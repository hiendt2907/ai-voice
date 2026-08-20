// CI/CD for DoctorCheck AI Call System — builds the 3 images (api, portal,
// voice), pushes to the in-cluster Harbor, then rewrites deploy/k8s's image
// tags and pushes back to Gitea for ArgoCD to pick up (sync stays manual —
// same convention as the omni-core Application on this cluster).
//
// Job setup mirrors omni-gcp-deploy: "Pipeline script from SCM", credential
// `gitea-hiendang`, scriptPath `Jenkinsfile`. Triggered manually (Build Now)
// for now — no webhook/poll configured, matching the existing convention.

pipeline {
    agent any

    environment {
        HARBOR   = 'harbor.harbor.svc.cluster.local/ai-voice'
        GIT_SHA  = "${GIT_COMMIT.take(7)}"
    }

    stages {
        stage('Build images') {
            steps {
                sh """
                    docker build -f apps/api/Dockerfile -t ${HARBOR}/api:${GIT_SHA} -t ${HARBOR}/api:latest .
                    docker build -f apps/portal/Dockerfile -t ${HARBOR}/portal:${GIT_SHA} -t ${HARBOR}/portal:latest .
                    docker build -f services/voice/Dockerfile -t ${HARBOR}/voice:${GIT_SHA} -t ${HARBOR}/voice:latest services/voice/
                """
            }
        }

        stage('Push to Harbor') {
            steps {
                // `docker login` always attempts HTTPS regardless of the
                // dind daemon's --insecure-registry config (a different
                // code path from push/pull) — confirmed live 2026-08-10 in
                // omni-gcp-deploy's Jenkinsfile, same fix applied here:
                // write ~/.docker/config.json directly instead of logging in.
                withCredentials([usernamePassword(
                    credentialsId: 'harbor-ai-voice-robot',
                    usernameVariable: 'HARBOR_USER',
                    passwordVariable: 'HARBOR_PASS'
                )]) {
                    sh """
                        mkdir -p ~/.docker
                        AUTH=\$(printf '%s:%s' "\$HARBOR_USER" "\$HARBOR_PASS" | base64 -w0)
                        cat > ~/.docker/config.json <<EOF
{"auths":{"${HARBOR.split('/')[0]}":{"auth":"\$AUTH"}}}
EOF
                        docker push ${HARBOR}/api:${GIT_SHA}
                        docker push ${HARBOR}/api:latest
                        docker push ${HARBOR}/portal:${GIT_SHA}
                        docker push ${HARBOR}/portal:latest
                        docker push ${HARBOR}/voice:${GIT_SHA}
                        docker push ${HARBOR}/voice:latest
                    """
                }
            }
        }

        stage('Update manifests (GitOps)') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'gitea-hiendang',
                    usernameVariable: 'GITEA_USER',
                    passwordVariable: 'GITEA_PASS'
                )]) {
                    sh """
                        cd deploy/k8s
                        sed -i "s#newTag: .*#newTag: ${GIT_SHA}#" kustomization.yaml
                        cd ../..
                        git config user.email "jenkins@ai-voice.local"
                        git config user.name "jenkins"
                        git add deploy/k8s/kustomization.yaml
                        if ! git diff --cached --quiet; then
                          git commit -m "ci: deploy ai-voice \${GIT_SHA} [skip ci]"
                          git push http://\$GITEA_USER:\$GITEA_PASS@gitea.cicd.svc.cluster.local:3000/hiendang/ai-voice.git HEAD:main
                        else
                          echo "No manifest change (tag already \${GIT_SHA})"
                        fi
                    """
                }
            }
        }
    }

    post {
        success {
            echo "Pushed ${HARBOR}/{api,portal,voice}:${GIT_SHA} — sync the 'ai-voice' ArgoCD Application to deploy (manual, by design)."
        }
    }
}
