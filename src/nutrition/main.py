import requests
import json
import os
import time
import boto3
from scipy import interpolate
import numpy as np
from decimal import Decimal
from datetime import datetime, timedelta

# Retrieve project and AWS session token from environment variables
PROJECT_NAME = os.getenv('PROJECT_NAME')
AWS_SESSION_TOKEN = os.getenv('AWS_SESSION_TOKEN')

# Define API URLs
SSM_URL = 'http://localhost:2773/systemsmanager/parameters/get?withDecryption=true&name='
BASE_URL = 'https://intervals.icu/api/v1/athlete/'
SNS_TOPIC = os.getenv('SNS_TOPIC')
NOTIFICATIONS_ENABLED = os.getenv('NOTIFICATIONS_ENABLED')

SNS_CLIENT = boto3.client('sns')

# Athlete parameters
WEIGHT_LOSS = #SET ME
ACTIVITY_LEVEL = #SET ME
HEIGHT = #SET_ME
TT_100M_SECS = #SET_ME
SWIM_LEVEL = #SET ME

# BMR constants
CALORIE_FLOOR = 1600
CALORIE_DEFICIT = {
    'aggressive': 750,
    'mild': 500,
    'low': 250
    }
ACTIVITY_MULTIPLIERS = {
    'sedentary': 1.2,
    'lightly_active': 1.375,
    'moderately_active': 1.55,
    'very_active': 1.725,
    'extra_active': 1.9
}

# Data for swimming VO2 calculations based on skill level
# https://alancouzens.blogspot.com/2010/01/are-you-skilled-swimmer.html
SWIM_VO2_DATA = {
    'skilled': {'x_val': [51, 55, 61, 64, 70, 78, 87], 'y_val': [6.3, 5.7, 5.1, 4.4, 3.8, 3.2, 2.5]},
    'triathlete': {'x_val': [66, 69, 75, 82, 90, 100, 109], 'y_val': [6.3, 5.7, 5.1, 4.4, 3.8, 3.2, 2.5]},
    'unskilled': {'x_val': [87, 92, 96, 103, 110, 118, 127], 'y_val': [6.3, 5.7, 5.1, 4.4, 3.8, 3.2, 2.5]}
}

def get_ssm_param(param_name):
    """Retrieve parameter from AWS SSM."""
    headers = {'X-Aws-Parameters-Secrets-Token': AWS_SESSION_TOKEN}
    for _ in range(5):
        response = requests.get(f'{SSM_URL}{param_name}', headers=headers)
        if response.ok:
            return json.loads(response.text).get('Parameter', {}).get('Value')
        time.sleep(0.1)
    raise Exception("Failed to fetch parameter after multiple attempts.")

def fetch_data(url, auth_key, retries=3, delay=2):
    """Fetch data from an API with retries."""
    for attempt in range(retries):
        response = requests.get(url, auth=('API_KEY', auth_key))
        if response.ok:
            return json.loads(response.text, parse_float=Decimal)
        time.sleep(delay)
    return None

def process_athlete_data(athlete):
    """Process athlete data."""
    athlete_settings = {
        'sex': athlete['sex'],
        'weight': float(athlete['icu_weight']),
        'age': datetime.now().year - datetime.strptime(athlete['icu_date_of_birth'], '%Y-%m-%d').year
    }

    sport_settings = athlete['sportSettings']
    for sport in sport_settings:
        sport_type = sport['types'][0]
        threshold_pace = sport.get('threshold_pace')
        pace_units = sport.get('pace_units')
        ftp = sport.get('ftp')

        if threshold_pace:
            if pace_units == 'MINS_KM':
                threshold_pace = round(1000 / (threshold_pace * 60), 2)
            elif pace_units == 'SECS_100M':
                threshold_pace = round(100 / (threshold_pace * 60), 2)
            else:
                threshold_pace = None

        if sport_type == 'Run':
            athlete_settings['run_threshold'] = float(threshold_pace)
        elif sport_type == 'Ride':
            athlete_settings['bike_threshold'] = float(ftp)
        elif sport_type == 'Swim':
            athlete_settings['swim_threshold'] = float(threshold_pace)

    return athlete_settings

def calculate_bmr(weight_kg, height_cm, age, sex):
    """Calculate the athletes Basal Metabolic Rate (BMR)."""
    adj_factor = 5.0 if sex == 'M' else -161
    return (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + adj_factor

def calculate_tdee(bmr, ACTIVITY_LEVEL):
    """Calculate the athletes TDEE using their BMR and their activity level."""
    return bmr * ACTIVITY_MULTIPLIERS.get(ACTIVITY_LEVEL, 1.2)

def calculate_expenditure(expenditure_type, power, duration, weight_kg, bike_economy=75, run_economy=210):
    """Calculate the expenditure of an activity."""
    if expenditure_type == 'run':
        liters_o2_per_min = ((run_economy / power) * weight_kg) / 1000
    elif expenditure_type == 'bike':
        liters_o2_per_min = power / bike_economy
    elif expenditure_type == 'swim':
        x_val = np.array(SWIM_VO2_DATA[SWIM_LEVEL]['x_val'])
        y_val = np.array(SWIM_VO2_DATA[SWIM_LEVEL]['y_val'])
        spline = interpolate.InterpolatedUnivariateSpline(x_val, y_val, k=3)
        predicted_cost = spline(TT_100M_SECS)
        liters_o2_per_min = predicted_cost
    kcals_per_min = liters_o2_per_min * 5
    return kcals_per_min * duration * 60

def calculate_cho(threshold, intensity_factor, planned_hrs):
    """Calculate the carbohydate requirements for the day."""
    if threshold <= 200:
        cho = 10
    elif threshold <= 240:
        cho = 11
    elif threshold <= 270:
        cho = 12
    elif threshold <= 300:
        cho = 13
    elif threshold <= 330:
        cho = 14
    elif threshold <= 360:
        cho = 15
    else:
        cho = 16
    tss = (intensity_factor**2) * 100 * planned_hrs
    cho_calories = tss * cho
    cho_grams = round(cho_calories/4)
    return cho_grams

def calculate_pro(weight_kg, planned_hours, WEIGHT_LOSS):
    """Calculate the protein requirements for the day."""
    if WEIGHT_LOSS:
        pro = 0.8 #change this to 1, lowered this to reduce protein amount while losing weight
    elif planned_hours < 1:
        pro = 0.7
    elif planned_hours < 2:
        pro = 0.8
    elif planned_hours < 2.5:
        pro = 0.9
    else:
        pro = 1
    pro_grams = round((weight_kg * 2.2) * pro)
    return pro_grams

def generate_nutrition_plan(athlete, workouts):
    """Generate a nutrition plan for the given athlete and workouts."""
    bmr = calculate_bmr(athlete['weight'], HEIGHT, athlete['age'], athlete['sex'])
    tdee = calculate_tdee(bmr, ACTIVITY_LEVEL)
    iee = tdee - CALORIE_DEFICIT.get('aggressive') if WEIGHT_LOSS else tdee

    nutrition_plan = {}

    for day, daily_workouts in workouts.items():
        workout_totals = {'Ride': {'sessions': 0, 'power': 0, 'hours': 0}, 'Run': {'sessions': 0, 'pace': 0, 'hours': 0}, 'Swim': {'sessions': 0, 'pace': 0, 'hours': 0}}

        workouts = [workout.get('type') for workout in daily_workouts]
        
        for workout in daily_workouts:
            workout_type = workout.get('type')
            if workout_type == 'Rest':
                continue

            total_time = workout.get('time', 0) / 3600  # Convert time to hours
            intensity = float(workout.get('intensity', 0))

            if workout_type == 'Run':
                workout_totals['Run']['pace'] += athlete['run_threshold'] / (intensity / 100) if intensity else 0
                workout_totals['Run']['hours'] += total_time
                workout_totals['Run']['sessions'] += 1
            elif workout_type == 'Ride':
                workout_totals['Ride']['power'] += (intensity / 100) * athlete['bike_threshold']
                workout_totals['Ride']['hours'] += total_time
                workout_totals['Ride']['sessions'] += 1
            elif workout_type == 'Swim':
                workout_totals['Swim']['pace'] += athlete['swim_threshold'] / (intensity / 100) if intensity else 0
                workout_totals['Swim']['hours'] += total_time
                workout_totals['Swim']['sessions'] += 1

        # Calculate averages and expenditures
        bike_power = (workout_totals['Ride']['power'] / workout_totals['Ride']['sessions']) if workout_totals['Ride']['sessions'] else 0
        run_pace = (workout_totals['Run']['pace'] / workout_totals['Run']['sessions']) if workout_totals['Run']['sessions'] else 0
        swim_pace = (workout_totals['Swim']['pace'] / workout_totals['Swim']['sessions']) if workout_totals['Swim']['sessions'] else 0

        total_kcal = iee + sum([
            calculate_expenditure('bike', bike_power, workout_totals['Ride']['hours'], athlete['weight']) if workout_totals['Ride']['sessions'] else 0,
            calculate_expenditure('run', run_pace, workout_totals['Run']['hours'], athlete['weight']) if workout_totals['Run']['sessions'] else 0,
            calculate_expenditure('swim', swim_pace, workout_totals['Swim']['hours'], athlete['weight']) if workout_totals['Swim']['sessions'] else 0
        ])
        total_kcal = max(total_kcal, CALORIE_FLOOR)
        total_hrs = workout_totals['Ride']['hours'] + workout_totals['Run']['hours'] + workout_totals['Swim']['hours']

        bike_intensity_factor = bike_power / athlete['bike_threshold'] if workout_totals['Ride']['hours'] else 0
        run_intensity_factor = athlete['run_threshold'] / run_pace if workout_totals['Run']['hours'] else 0
        swim_intensity_factor = athlete['swim_threshold'] / swim_pace if workout_totals['Swim']['hours'] else 0  

        try:
            average_intensity_factor = ((bike_intensity_factor * workout_totals['Ride']['hours']) + (run_intensity_factor * workout_totals['Run']['hours']) + (swim_intensity_factor * workout_totals['Swim']['hours'])) / (workout_totals['Ride']['hours'] + workout_totals['Run']['hours'] + workout_totals['Swim']['hours'])
        except ZeroDivisionError:
            average_intensity_factor = 0

        cho = calculate_cho(athlete['bike_threshold'], average_intensity_factor, total_hrs) if total_hrs else 50
        pro = calculate_pro(athlete['weight'], total_hrs, WEIGHT_LOSS)
        fat = round((total_kcal - (cho * 4) - (pro * 4)) / 9)

        nutrition_plan[day] = {'Workouts': workouts, 'Total Calories': round(total_kcal), 'CHO': cho, 'PRO': pro, 'FAT': fat}

    return nutrition_plan

def create_date_range_dict(start_date, end_date):
    """Creates a dict for each date between start_date and end_date."""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    return { (start + timedelta(days=x)).strftime('%Y-%m-%d'): [{'type': 'Rest'}] for x in range((end - start).days + 1) }

def notify(nutrition_plan):
    """Format and send notification message."""

    message = (
        f"<b>Nutrition Plan:</b>\n\n" +
        "\n".join(f"<b>{day}</b>\nWorkouts: {','.join(items['Workouts'])}\nCalories: {items['Total Calories']}\nMacros: CHO - {items['CHO']} PRO - {items['PRO']} FAT - {items['FAT']}\n" for day, items in nutrition_plan.items())
    )
    print(message)
    if NOTIFICATIONS_ENABLED:
        SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Subject="Nutrition Plan", Message=message)

def main(event, context):
    intervals_api_key = get_ssm_param(f'/{PROJECT_NAME}/intervals/api_key')
    intervals_uid = get_ssm_param(f'/{PROJECT_NAME}/intervals/uid')

    if not intervals_api_key or not intervals_uid:
        print('Error retrieving API keys or user ID.')
        return

    user_data = fetch_data(f'{BASE_URL}{intervals_uid}', intervals_api_key)
    athlete_settings = process_athlete_data(user_data)

    today = datetime.today()
    #This gets next Monday, undecided whether to run this on a Sunday evening or on a Monday morning?
    # next_monday = today + timedelta(days=(7 - today.weekday())) if today.weekday() != 0 else today + timedelta(weeks=1)
    next_monday = today
    next_sunday = next_monday + timedelta(days=6)
    export_from = next_monday.strftime('%Y-%m-%d')
    export_to = next_sunday.strftime('%Y-%m-%d')

    planned_week = create_date_range_dict(export_from, export_to)
    workouts = fetch_data(f'{BASE_URL}{intervals_uid}/events?category=WORKOUT&oldest={export_from}&newest={export_to}', intervals_api_key)

    if workouts:
        for workout in workouts:
            workout_date = workout['start_date_local'].split('T')[0]  # Extract date from workoutDay
            if workout_date in planned_week:
                workout_trimmed = {'type': workout['type'], 'intensity': workout['icu_intensity'], 'time': workout['moving_time'], 'distance': workout['distance']}
                # If the date already has a workout, append the new workout to the list
                if isinstance(planned_week[workout_date], list):
                    planned_week[workout_date].append(workout_trimmed)
                else:
                    # If there's only one workout on the date, create a list with this workout
                    planned_week[workout_date] = [planned_week[workout_date], workout_trimmed]

                # Remove 'Rest' type if workouts exist for the date
                if isinstance(planned_week[workout_date], list):
                    planned_week[workout_date] = [w for w in planned_week[workout_date] if not (isinstance(w, dict) and w.get('type') == 'Rest')] 
 
    nutrition_plan = generate_nutrition_plan(athlete_settings, planned_week)
    notify(nutrition_plan)