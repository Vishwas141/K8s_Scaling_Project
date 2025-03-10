import time
import threading
from flask import Flask, jsonify
import numpy as np

app = Flask(__name__)

# Global variable to store simulated user count
current_user_count = 0

def heavy_computation():
    """Run heavy computation to simulate resource-intensive work."""
    while True:
        size = 1000  # Adjust the size for desired load
        A = np.random.rand(size, size)
        B = np.random.rand(size, size)
        C = np.dot(A, B)
        total = np.sum(C)
        print(f"Heavy computation result: {total}")
        time.sleep(5)

def simulate_user_count():
    """Independently simulate the user count.
    
    You can modify this function to include trends, random spikes, or other simulation logic.
    """
    global current_user_count
    while True:
        # For example, simulate a user count as a random integer between 0 and 10.
        # You could also add logic for occasional spikes.
        current_user_count = np.random.randint(0, 10)
        
        # Example spike simulation: with a 20% chance, add a random spike (between 10 and 30)
        if np.random.rand() < 0.2:
            spike = np.random.randint(10, 30)
            current_user_count += spike
            print(f"Spike introduced: {spike}")
            
        print(f"Simulated user count: {current_user_count}")
        time.sleep(5)

@app.route('/user_count', methods=['GET'])
def get_user_count():
    """Endpoint to return the current simulated user count."""
    return jsonify({"user_count": current_user_count})

@app.route('/')
def index():
    return "Resource Intensive Custom App Running"

if __name__ == '__main__':
    # Start the heavy computation in a background thread (for CPU load simulation)
    heavy_thread = threading.Thread(target=heavy_computation)
    heavy_thread.daemon = True
    heavy_thread.start()

    # Start the user count simulation in its own thread
    user_count_thread = threading.Thread(target=simulate_user_count)
    user_count_thread.daemon = True
    user_count_thread.start()

    # Run the Flask server on port 6000
    app.run(host='0.0.0.0', port=6000)
