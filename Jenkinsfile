pipeline {
    agent any

    environment {
        REGISTRY      = '192.168.147.105:8082'
        IMAGE_NAME    = 'aqua-rolltable'
        IMAGE_TAG     = "${env.BUILD_NUMBER}"
        FULL_IMAGE    = "${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
        AQUA_HOST     = 'https://192.168.147.105'
        SCANNER_IMAGE = 'registry.aquasec.com/scanner:2022.4.868'
        AQUA_CREDS_ID = 'aqua-console'
    }

    options {
        timeout(time: 15, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {

        stage('Build Image') {
            steps {
                sh '''
                    set -eux
                    podman build \
                        --tag ${FULL_IMAGE} \
                        --label build.number=${BUILD_NUMBER} \
                        --label build.url=${BUILD_URL} \
                        .
                '''
            }
        }

        stage('Push to Registry') {
            steps {
                sh '''
                    set -eux
                    podman push ${FULL_IMAGE} --tls-verify=false
                '''
            }
        }

        stage('Aqua Security Scan') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: "${AQUA_CREDS_ID}",
                    usernameVariable: 'AQUA_USER',
                    passwordVariable: 'AQUA_PASSWORD'
                )]) {
                    sh '''
                        set -eux
                        podman run --rm --network host \
                            --security-opt label=disable --user root \
                            -v /var/run/docker.sock:/var/run/docker.sock \
                            ${SCANNER_IMAGE} \
                            scan \
                                --host ${AQUA_HOST} \
                                --local ${FULL_IMAGE} \
                                --no-verify \
                                --user ${AQUA_USER} \
                                --password ${AQUA_PASSWORD} \
                                --html > aqua-report.html

                        echo "--- Aqua scan summary ---"
                        grep -oE "Image Is (Compliant|Non-compliant)" aqua-report.html || true
                        # Hard CI/CD gate: pipeline only proceeds if image is Compliant.
                        grep -q "Image Is Compliant" aqua-report.html \
                            || { echo "BLOCKED: image is non-compliant (or scan report missing compliance marker)"; exit 1; }
                    '''
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: 'aqua-report.html',
                                     allowEmptyArchive: true
                }
            }
        }

        stage('Deploy & Verify Webpage') {
            steps {
                sh '''
                    set -eux
                    podman run -d --name aqua-rolltable-verify-${BUILD_NUMBER} \
                        --network host \
                        ${FULL_IMAGE}
                    if curl -fsS --retry 15 --retry-delay 1 --retry-connrefused \
                            http://192.168.147.105:8084/ \
                        | grep -qi "<title>Lunch"; then
                        echo "Webpage verified: HTTP 200 + Lunch page title"
                    else
                        echo "BLOCKED: lunch page title missing or page not served"
                        echo "--- container state ---"
                        podman inspect -f '{{.State.Status}} (exit={{.State.ExitCode}})' \
                            aqua-rolltable-verify-${BUILD_NUMBER} || true
                        echo "--- container logs ---"
                        podman logs aqua-rolltable-verify-${BUILD_NUMBER} || true
                        exit 1
                    fi
                '''
            }
            post {
                always {
                    sh 'podman rm -f aqua-rolltable-verify-${BUILD_NUMBER} || true'
                }
            }
        }

        stage('Deploy (long-running)') {
            // Stand up the verified image as a persistent service. Stops any
            // previous long-running instance first so the port switches over
            // cleanly to the new build. Uses --restart=always so the page
            // survives host reboots. Lives at http://192.168.147.105:8084/.
            steps {
                sh '''
                    set -eux
                    podman rm -f aqua-rolltable || true
                    podman run -d --name aqua-rolltable \
                        --network host \
                        --restart=always \
                        ${FULL_IMAGE}
                    if curl -fsS --retry 15 --retry-delay 1 --retry-connrefused \
                            http://192.168.147.105:8084/ \
                        | grep -qi "<title>Lunch"; then
                        echo "Long-running deploy live at http://192.168.147.105:8084/"
                    else
                        echo "BLOCKED: long-running deploy did not serve the Lunch page"
                        podman inspect -f '{{.State.Status}} (exit={{.State.ExitCode}})' \
                            aqua-rolltable || true
                        podman logs aqua-rolltable || true
                        exit 1
                    fi
                '''
            }
        }
    }

    post {
        always {
            sh 'podman rmi ${FULL_IMAGE} || true'
        }
        success {
            echo "Pipeline SUCCESS — image ${FULL_IMAGE} passed Aqua scan (HTML report archived)"
            emailext (
                subject: "✅ Build #${BUILD_NUMBER} PASSED — ${FULL_IMAGE}",
                body: """<h2>Aqua Security CI/CD — Build #${BUILD_NUMBER} PASSED</h2>
                    <p>Image: <code>${FULL_IMAGE}</code></p>
                    <p>Aqua scan result: <b>Image Is Compliant</b></p>
                    <p>Deploy verify: Lunch page OK on <code>192.168.147.105:8084/</code></p>
                    <p>Report: <a href=\"${BUILD_URL}artifact/aqua-report.html\">aqua-report.html</a><br>
                       Console: <a href=\"${BUILD_URL}console\">build console</a><br>
                       Build: <a href=\"${BUILD_URL}\">#${BUILD_NUMBER}</a></p>
                """,
                mimeType: 'text/html',
                to: 'tim.wong@systex.com.hk'
            )
        }
        failure {
            echo "Pipeline FAILED — see Aqua scan results above for the vulnerabilities that triggered the failure"
            emailext (
                subject: "❌ Build #${BUILD_NUMBER} FAILED",
                body: """<h2>Aqua Security CI/CD — Build #${BUILD_NUMBER} FAILED</h2>
                    <p>Image: <code>${FULL_IMAGE}</code></p>
                    <p>Check the console for the failure stage.</p>
                    <p>Console: <a href=\"${BUILD_URL}console\">build console</a><br>
                       Build: <a href=\"${BUILD_URL}\">#${BUILD_NUMBER}</a></p>
                """,
                mimeType: 'text/html',
                attachLog: true,
                to: 'tim.wong@systex.com.hk'
            )
        }
    }
}
