# Start Minikube
minikube start

# Enable the metrics-server addon in Minikube
minikube addons enable metrics-server

# Clone the repository
git clone https://github.com/Vishwas141/k8s_resource_monitoring.git
cd k8s_resource_monitoring

# Check the local machine IP
hostname -I  # Take the first IP from the output

# Replace the first IP in `base_url` inside `custom-scaler.py`

# Build Docker images
docker build -t custom-k8s-scaler:latest -f Dockerfile.scaler .


docker build -t custom-app:latest -f Dockerfile.app .

# Load images into Minikube
minikube image load custom-k8s-scaler:latest
minikube image load custom-app:latest

# Apply Kubernetes manifests
kubectl apply -f k8s-manifests.yaml

# Verify deployments and pods
kubectl get deployments
kubectl get pods

# Forward the service port for external access
kubectl port-forward service/custom-scaler-service 8080:80

#check /data for the accessing user pod count and /metric for the cpu_usage and memory_usage
