# Travel Time Optimizer

A Flask web app to optimize travel times in Hyderabad, India, using TomTom APIs for routing and Weatherstack for weather data. Calculates the best departure time to reach your destination by a specified arrival time, factoring in traffic and weather.

## Features
- Input source, destination, arrival time, and travel mode (car, motorcycle, bicycle, pedestrian).
- Suggests optimal departure time and an optional faster alternative.
- Includes weather impact (precipitation, temperature) and traffic alerts.
- Links to Google Maps for route visualization.

## Next Steps
- Add more travel modes or API integrations (e.g., public transit).
- Improve UI with CSS or a frontend framework.
- Cache API responses for faster performance.

## Running the Project
1. Clone the repo:
git clone https://github.com/Sahithi-Kallem/TravelTimeOptimiser.git cd TravelTimeOptimiser

2. Install dependencies:
pip install -r requirements.txt

3. Run the app:
python app.py

4. Open `http://127.0.0.1:5000/` in your browser.

## Dependencies
- Flask: Web framework
- NumPy: Time calculations
- Requests: API calls