from kubernetes import client, config
from prometheus_client import start_http_server, Gauge
import time
import numpy as np
from sklearn.linear_model import LinearRegression
import os
from flask import Flask, render_template_string, jsonify
from threading import Thread
import requests

app = Flask(__name__)

try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

apps_v1 = client.AppsV1Api()

NAMESPACE = os.getenv('NAMESPACE', 'default')
DEPLOYMENT_NAME = os.getenv('DEPLOYMENT_NAME', 'example-deployment')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '10'))
PREDICTION_WINDOW = int(os.getenv('PREDICTION_WINDOW', '5'))
SCALE_THRESHOLD = float(os.getenv('SCALE_THRESHOLD', '0.6'))
SPIKE_THRESHOLD = float(os.getenv('SPIKE_THRESHOLD', '50'))
USERS_PER_POD = int(os.getenv('USERS_PER_POD', '3'))
MIN_PODS = int(os.getenv('MIN_PODS', '2'))
MAX_PODS = int(os.getenv('MAX_PODS', '400'))
SCALE_INCREMENT = int(os.getenv('SCALE_INCREMENT', '5'))
CPU_THRESHOLD = float(os.getenv('CPU_THRESHOLD', '700'))  # mCPU
MEMORY_THRESHOLD = float(os.getenv('MEMORY_THRESHOLD', '300'))  # MiB

user_count = Gauge('user_count', 'Number of active users')
pod_count = Gauge('pod_count', 'Number of active pods')

base_url = "http://10.13.2.28:5000"

def get_current_user_count():
    try:
        url = "http://custom-app-service:6000/user_count"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            value = float(data.get("user_count", 0))
            user_count.set(value)
            return value
        else:
            print("Non-200 response from custom app:", response.status_code)
    except Exception as e:
        print("Error fetching user count from custom app:", e)

    change = np.random.randint(-5, 10)
    current_value = user_count._value.get() + change
    user_count.set(max(0, current_value))
    return float(current_value)

def get_resource():
    try:
        response = requests.get(base_url, timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            print("Non-200 response:", response.status_code)
            return {"error": f"Non-200 response: {response.status_code}"}
    except Exception as e:
        print("Error fetching data:", e)
        return {"error": str(e)}

def get_current_pod_count():
    try:
        deployment = apps_v1.read_namespaced_deployment(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE
        )
        return deployment.spec.replicas
    except Exception as e:
        print(f"Error getting pod count: {e}")
        return 0

def calculate_desired_pods(current_users):
    return max(MIN_PODS, min(MAX_PODS, -(-current_users // USERS_PER_POD)))

def predict_trend(historical_data):
    if len(historical_data) < PREDICTION_WINDOW:
        return 0
    X = np.array(range(len(historical_data))).reshape(-1, 1)
    y = np.array(historical_data)
    model = LinearRegression()
    model.fit(X, y)
    return model.coef_[0]

def detect_spike(historical_data):
    if len(historical_data) < 2:
        return False
    delta = abs(historical_data[-1] - historical_data[-2])
    return delta > SPIKE_THRESHOLD

def hybrid_scaling(historical_data, current_users):
    direct_pods = calculate_desired_pods(current_users)
    regression_pods = direct_pods
    if len(historical_data) >= PREDICTION_WINDOW:
        trend = predict_trend(historical_data)
        regression_pods = calculate_desired_pods(current_users + trend * PREDICTION_WINDOW)
    desired_pods = max(direct_pods, regression_pods)
    if detect_spike(historical_data):
        print("Spike detected! Scaling conservatively.")
        desired_pods = min(desired_pods + SCALE_INCREMENT, MAX_PODS)
    return desired_pods

def resource_based_scaling(metrics, current_replicas):
    total_cpu_usage_mCPU = metrics.get("total_cpu_usage_mCPU", 0)
    total_memory_usage_MiB = metrics.get("total_memory_usage_MiB", 0)

    if total_cpu_usage_mCPU > CPU_THRESHOLD or total_memory_usage_MiB > MEMORY_THRESHOLD:
        print(f"Resource threshold exceeded: CPU {total_cpu_usage_mCPU} mCPU, Memory {total_memory_usage_MiB} MiB")
        return max(current_replicas + SCALE_INCREMENT, MAX_PODS)
    return current_replicas

def scale_deployment(desired_replicas):
    try:
        deployment = apps_v1.read_namespaced_deployment(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE
        )
        current_replicas = deployment.spec.replicas
        if desired_replicas != current_replicas:
            deployment.spec.replicas = desired_replicas
            apps_v1.patch_namespaced_deployment(
                name=DEPLOYMENT_NAME,
                namespace=NAMESPACE,
                body=deployment
            )
            print(f"Scaled deployment from {current_replicas} to {desired_replicas} pods")
            pod_count.set(desired_replicas)
        else:
            print(f"No scaling required. Current replicas: {current_replicas}")
    except Exception as e:
        print(f"Error scaling deployment: {e}")

def scaler_loop():
    historical_data = []
    while True:
        current_users = get_current_user_count()
        historical_data.append(current_users)
        if len(historical_data) > PREDICTION_WINDOW:
            historical_data.pop(0)

        # First, scale based on user-pod algorithm
        desired_replicas = hybrid_scaling(historical_data, current_users)
        scale_deployment(desired_replicas)

        # Then, check resource usage and scale if necessary
        metrics = get_resource()
        if metrics and "error" not in metrics:
            desired_replicas = resource_based_scaling(metrics, desired_replicas)
            scale_deployment(desired_replicas)

        print(f"User count: {current_users}, Pod count: {get_current_pod_count()}")
        time.sleep(CHECK_INTERVAL)

@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Kubernetes Scaler Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { text-align: center; }
            .chart-container { width: 100%; height: 400px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Kubernetes Scaler Dashboard</h1>
            <div class="chart-container">
                <canvas id="userPodChart"></canvas>
            </div>
            <h2>Resource Usage</h2>
            <div class="chart-container">
                <canvas id="resourceChart"></canvas>
            </div>
        </div>
        <script>
            const ctx1 = document.getElementById('userPodChart').getContext('2d');
            const userPodChart = new Chart(ctx1, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'User Count',
                        data: [],
                        borderColor: 'rgb(75, 192, 192)',
                        tension: 0.1
                    }, {
                        label: 'Pod Count',
                        data: [],
                        borderColor: 'rgb(255, 99, 132)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });

            const ctx2 = document.getElementById('resourceChart').getContext('2d');
            const resourceChart = new Chart(ctx2, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'CPU Usage (mCPU)',
                        data: [],
                        borderColor: 'rgb(54, 162, 235)',
                        tension: 0.1
                    }, {
                        label: 'Memory Usage (MiB)',
                        data: [],
                        borderColor: 'rgb(255, 159, 64)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });

            function updateCharts() {
                fetch('/data')
                    .then(response => response.json())
                    .then(data => {
                        const now = new Date().toLocaleTimeString();
                        userPodChart.data.labels.push(now);
                        userPodChart.data.datasets[0].data.push(data.user_count);
                        userPodChart.data.datasets[1].data.push(data.pod_count);
                        if (userPodChart.data.labels.length > 20) {
                            userPodChart.data.labels.shift();
                            userPodChart.data.datasets[0].data.shift();
                            userPodChart.data.datasets[1].data.shift();
                        }
                        userPodChart.update();
                    });
                
                fetch('/metric')
                    .then(response => response.json())
                    .then(data => {
                        const now = new Date().toLocaleTimeString();
                        resourceChart.data.labels.push(now);
                        resourceChart.data.datasets[0].data.push(data.total_cpu_usage_mCPU || 0);
                        resourceChart.data.datasets[1].data.push(data.total_memory_usage_MiB || 0);
                        if (resourceChart.data.labels.length > 20) {
                            resourceChart.data.labels.shift();
                            resourceChart.data.datasets[0].data.shift();
                            resourceChart.data.datasets[1].data.shift();
                        }
                        resourceChart.update();
                    });
            }
            setInterval(updateCharts, 5000);
        </script>
    </body>
    </html>
    ''')
@app.route('/data')
def data():
    return jsonify({
        'user_count': user_count._value.get(),
        'pod_count': pod_count._value.get()
    })

@app.route('/metric')
def resource_data():
    return jsonify(get_resource())

def main():
    print(f"Starting custom scaler for deployment {DEPLOYMENT_NAME} in namespace {NAMESPACE}")
    start_http_server(8000)
    scaler_thread = Thread(target=scaler_loop)
    scaler_thread.start()
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()