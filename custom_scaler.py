from kubernetes import client, config
from prometheus_client import start_http_server, Gauge
import time
import numpy as np
from sklearn.linear_model import LinearRegression
import os
from flask import Flask, render_template_string, jsonify
from threading import Thread
import requests  # newly added

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
    
user_count = Gauge('user_count', 'Number of active users')
pod_count = Gauge('pod_count', 'Number of active pods')

def get_current_user_count():
    try:
        # Call the custom app's user_count endpoint via its service DNS
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

def scale_deployment_with_hybrid(current_users, historical_data):
    try:
        deployment = apps_v1.read_namespaced_deployment(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE
        )
        current_replicas = deployment.spec.replicas
        desired_replicas = hybrid_scaling(historical_data, current_users)
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
        print(f"User count: {current_users}, Pod count: {get_current_pod_count()}")
        scale_deployment_with_hybrid(current_users, historical_data)
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
                <canvas id="myChart"></canvas>
            </div>
        </div>
        <script>
            const ctx = document.getElementById('myChart').getContext('2d');
            const chart = new Chart(ctx, {
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
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
            function updateChart() {
                fetch('/data')
                    .then(response => response.json())
                    .then(data => {
                        const now = new Date().toLocaleTimeString();
                        chart.data.labels.push(now);
                        chart.data.datasets[0].data.push(data.user_count);
                        chart.data.datasets[1].data.push(data.pod_count);
                        if (chart.data.labels.length > 20) {
                            chart.data.labels.shift();
                            chart.data.datasets[0].data.shift();
                            chart.data.datasets[1].data.shift();
                        }
                        chart.update();
                    });
            }
            setInterval(updateChart, 5000);
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

def main():
    print(f"Starting custom scaler for deployment {DEPLOYMENT_NAME} in namespace {NAMESPACE}")
    start_http_server(8000)
    scaler_thread = Thread(target=scaler_loop)
    scaler_thread.start()
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()
