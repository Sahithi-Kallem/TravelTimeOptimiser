from flask import Flask, request, render_template
import requests
import numpy as np
from datetime import datetime, timedelta
import json
from functools import lru_cache
import os  # Add this for environment variables

app = Flask(__name__)
tomtom_key = os.getenv("TOMTOM_API_KEY")  # Get from env
weather_key = os.getenv("WEATHERSTACK_API_KEY")  # Get from env

@lru_cache(maxsize=128)
def get_coordinates(address):
    full_address = f"{address}, Hyderabad, India"
    url = f"https://api.tomtom.com/search/2/geocode/{full_address}.json?key={tomtom_key}&limit=1"
    resp = requests.get(url).json()
    if "results" in resp and resp["results"]:
        pos = resp["results"][0]["position"]
        print(f"Geocoded {full_address}: {pos['lat']}, {pos['lon']}")
        return pos["lat"], pos["lon"]
    print(f"Geocoding failed for {full_address}: {resp}")
    return None, None

@lru_cache(maxsize=128)
def get_travel_time(source_coords, dest_coords, depart_at, travel_mode):
    url = f"https://api.tomtom.com/routing/1/calculateRoute/{source_coords}:{dest_coords}/json?key={tomtom_key}&traffic=true&departAt={depart_at}&travelMode={travel_mode}"
    resp = requests.get(url).json()
    if "routes" in resp and resp["routes"]:
        route = resp["routes"][0]
        summary = route["summary"]
        print(f"Route from {source_coords} to {dest_coords} at {depart_at}: {summary['travelTimeInSeconds']/60.0} min, {summary['lengthInMeters']/1000.0} km")
        return summary["travelTimeInSeconds"] / 60.0, summary["lengthInMeters"] / 1000.0
    print(f"Routing failed: {resp}")
    return None, None

def get_weather_impact(source_lat, source_lon, dest_lat, dest_lon, arrival_time_str):
    today = datetime.now().strftime("%Y-%m-%d")
    for lat, lon in [(source_lat, source_lon), (dest_lat, dest_lon)]:
        url = f"http://api.weatherstack.com/forecast?access_key={weather_key}&query={lat},{lon}&forecast_days=1&hourly=1"
        resp = requests.get(url).json()
        if "forecast" in resp and today in resp["forecast"]:
            forecast = resp["forecast"][today]["hourly"]
            hour = int(arrival_time_str.split(":")[0])
            closest = min(forecast, key=lambda x: abs(int(x["time"]) // 100 - hour))
            yield closest["precip"], closest["temperature"]
        else:
            print(f"Weather fetch failed for {lat}, {lon}: {resp}")
            yield 0, 32

def get_traffic_incidents(source_coords, dest_coords):
    source_lat, source_lon = map(float, source_coords.split(','))
    dest_lat, dest_lon = map(float, dest_coords.split(','))
    padding = 0.05
    bbox = f"{min(source_lat, dest_lat) - padding},{min(source_lon, dest_lon) - padding},{max(source_lat, dest_lat) + padding},{max(source_lon, dest_lon) + padding}"
    url = f"https://api.tomtom.com/traffic/services/4/incidentDetails?key={tomtom_key}&bbox={bbox}&fields={{incidents{{description}}}}&language=en-GB"
    resp = requests.get(url)
    print(f"Traffic incidents raw response: {resp.text}")
    if resp.status_code == 200:
        try:
            data = resp.json()
            if "incidents" in data:
                return [inc["description"] for inc in data["incidents"] if "traffic" in inc["description"].lower()]
        except requests.exceptions.JSONDecodeError as e:
            print(f"Failed to decode traffic incidents JSON: {e}")
    print(f"Traffic incidents failed - Status: {resp.status_code}, Response: {resp.text}")
    return []

@app.route("/", methods=["GET", "POST"])
def optimize():
    min_date = datetime.now().strftime("%Y-%m-%d")
    default_date = min_date
    error_message = None

    if not tomtom_key or not weather_key:
        error_message = "API keys not set. Please configure TOMTOM_API_KEY and WEATHERSTACK_API_KEY environment variables."
        return render_template("index.html", source="", dest="", arrival_time="", travel_mode="car", arrival_date=default_date, min_date=min_date, error_message=error_message)

    if request.method == "POST":
        source = request.form["source"]
        dest = request.form["destination"]
        arrival_date = request.form["arrival_date"]
        arrival_time_str = request.form["arrival_time"]
        travel_mode = request.form["travel_mode"]
        
        try:
            arrival_dt = datetime.strptime(f"{arrival_date} {arrival_time_str}", "%Y-%m-%d %H:%M")
            if arrival_dt < datetime.now():
                error_message = "Arrival time must be in the future."
                return render_template("index.html", source=source, dest=dest, arrival_time=arrival_time_str, travel_mode=travel_mode, arrival_date=arrival_date, min_date=min_date, error_message=error_message)
            arrival_hour = arrival_dt.hour + arrival_dt.minute / 60.0
        except ValueError:
            error_message = "Invalid date or time format. Use YYYY-MM-DD and HH:MM (00:00-23:59)."
            return render_template("index.html", source=source, dest=dest, arrival_time=arrival_time_str, travel_mode=travel_mode, arrival_date=arrival_date, min_date=min_date, error_message=error_message)

        source_lat, source_lon = get_coordinates(source)
        dest_lat, dest_lon = get_coordinates(dest)
        if not (source_lat and dest_lat):
            error_message = "Couldn’t find coordinates for one or both addresses in Hyderabad."
            return render_template("index.html", source=source, dest=dest, arrival_time=arrival_time_str, travel_mode=travel_mode, arrival_date=arrival_date, min_date=min_date, error_message=error_message)

        source_coords = f"{source_lat},{source_lon}"
        dest_coords = f"{dest_lat},{dest_lon}"

        sample_duration, sample_distance = get_travel_time(source_coords, dest_coords, datetime.now().isoformat(), "car")
        if sample_distance:
            if travel_mode in ["pedestrian", "bicycle"] and sample_distance > 10:
                error_message = f"Distance ({sample_distance:.1f} km) too far for {travel_mode}. Max 10 km."
                return render_template("index.html", source=source, dest=dest, arrival_time=arrival_time_str, travel_mode=travel_mode, arrival_date=arrival_date, min_date=min_date, error_message=error_message)

        weather_data = list(get_weather_impact(source_lat, source_lon, dest_lat, dest_lon, arrival_time_str))
        precip = sum(w[0] for w in weather_data) / len(weather_data)
        temp = sum(w[1] for w in weather_data) / len(weather_data)

        now = datetime.now()
        base_date = arrival_dt.date()
        current_hour = now.hour + now.minute / 60.0 + now.second / 3600.0 if base_date == now.date() else 0
        window_size = 1.0
        earliest_start_hour = max(current_hour, arrival_hour - window_size)
        latest_start_hour = arrival_hour
        times = np.arange(earliest_start_hour, latest_start_hour + 1/12, 1/12)

        if len(times) == 0:
            error_message = f"No valid start times available to reach by {arrival_time_str}. Try a later arrival."
            return render_template("index.html", source=source, dest=dest, arrival_time=arrival_time_str, travel_mode=travel_mode, arrival_date=arrival_date, min_date=min_date, error_message=error_message)

        durations = []
        distances = []
        arrival_times = []
        print(f"Now: {current_hour:.4f}, Arrival: {arrival_hour:.4f}, Times: {times}")
        for t in times:
            h, m = divmod(int(t * 60), 60)
            depart_dt = datetime.combine(base_date, datetime.min.time()) + timedelta(hours=h, minutes=m)
            depart_at = depart_dt.isoformat()
            duration, distance = get_travel_time(source_coords, dest_coords, depart_at, travel_mode)
            if duration is None:
                error_message = "Error fetching travel time from TomTom."
                return render_template("index.html", source=source, dest=dest, arrival_time=arrival_time_str, travel_mode=travel_mode, arrival_date=arrival_date, min_date=min_date, error_message=error_message)
            if precip > 0.5:
                if travel_mode == "bicycle":
                    duration *= max(1.1, min(1.5, 1 + precip / 10))
                elif travel_mode == "motorcycle":
                    duration *= max(1.05, min(1.2, 1 + precip / 20))
                elif travel_mode == "car":
                    duration *= max(1.05, min(1.3, 1 + precip / 15))
                elif travel_mode == "pedestrian":
                    duration *= max(1.1, min(1.4, 1 + precip / 10))
            durations.append(duration)
            distances.append(distance)
            arrival_times.append(t + duration / 60.0)
        print(f"Arrival times: {arrival_times}")

        valid_starts = [(i, t) for i, t in enumerate(times) 
                        if arrival_times[i] <= arrival_hour + 1/60 and datetime.combine(base_date, datetime.min.time()) + timedelta(hours=t) >= now]
        
        if not valid_starts:
            min_duration = min(durations)
            min_idx = durations.index(min_duration)
            error_message = f"Travel takes {min_duration:.1f} min—too long to reach by {arrival_time_str}. Try a later arrival."
            return render_template("index.html", source=source, dest=dest, arrival_time=arrival_time_str, travel_mode=travel_mode, arrival_date=arrival_date, min_date=min_date, error_message=error_message)
        
        preferred_idx, preferred_time = max(valid_starts, key=lambda x: x[1])
        preferred_start_time = durations[preferred_idx]
        preferred_distance = distances[preferred_idx]
        preferred_start_h, preferred_start_m = divmod(int(preferred_time * 60), 60)
        preferred_start_str = f"{preferred_start_h:02d}:{preferred_start_m:02d}"

        valid_indices = [i for i, _ in valid_starts]
        valid_durations = [durations[i] for i in valid_indices]
        optimal_time = min(valid_durations)
        optimal_idx = valid_indices[valid_durations.index(optimal_time)]
        optimal_start_h, optimal_start_m = divmod(int(times[optimal_idx] * 60), 60)
        optimal_start_str = f"{optimal_start_h:02d}:{optimal_start_m:02d}"
        optimal_distance = distances[optimal_idx]
        time_saving = preferred_start_time - optimal_time

        if time_saving < 2:
            optimal_time = optimal_start_str = optimal_distance = None

        incidents = get_traffic_incidents(source_coords, dest_coords)
        alert = "Traffic’s spiking—leave 5 min earlier!" if incidents else None

        google_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={source_lat},{source_lon}&destination={dest_lat},{dest_lon}&travelmode={travel_mode}"

        display_date = arrival_dt.strftime("%A, %Y-%m-%d")
        return render_template("index.html", optimal_time=optimal_time, optimal_start=optimal_start_str, 
                             arrival_time=arrival_time_str, preferred_time=preferred_start_time, 
                             preferred_start=preferred_start_str, source=source, dest=dest, 
                             precip=precip, temp=temp, travel_mode=travel_mode, 
                             preferred_distance=preferred_distance, optimal_distance=optimal_distance, 
                             display_date=display_date, alert=alert, google_maps_url=google_maps_url,
                             arrival_date=arrival_date, min_date=min_date, error_message=error_message)
    return render_template("index.html", source="", dest="", arrival_time="", travel_mode="car", arrival_date=default_date, min_date=min_date, error_message=error_message)

if __name__ == "__main__":
    app.run(debug=True)