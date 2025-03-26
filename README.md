
docker build -t custom-k8s-scaler:latest -f Dockerfile.scaler .
docker build -t custom-app:latest -f Dockerfile.app .

minikube image load custom-k8s-scaler:latest
minikube image load custom-app:latest



kubectl apply -f k8s-manifests.yaml



kubectl get deployments
kubectl get pods

kubectl port-forward service/custom-scaler-service 8080:80
