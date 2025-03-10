Build the Docker Images

    Build the custom scaler image:

docker build -t custom-k8s-scaler:latest -f Dockerfile.scaler .

Build the custom app image:

    docker build -t custom-app:latest -f Dockerfile.app .

Load the Images into Minikube

minikube image load custom-k8s-scaler:latest
minikube image load custom-app:latest

Deploy to Kubernetes

kubectl apply -f k8s-manifests.yaml

Verify the Deployments

kubectl get deployments
kubectl get pods

Access the Services

    To view the custom scaler dashboard:

kubectl port-forward service/custom-scaler-service 8080:80
