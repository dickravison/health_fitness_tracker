import requests
import json
import os
import boto3
import botocore
import time
from decimal import Decimal
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# Environment Variables
PROJECT_NAME = os.getenv('PROJECT_NAME')
AWS_SESSION_TOKEN = os.getenv('AWS_SESSION_TOKEN')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE')

SSM_URL = 'http://localhost:2773/systemsmanager/parameters/get?withDecryption=true&name='
BASE_URL = 'https://intervals.icu/api/v1/athlete/'
FULL_IMPORT = False

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE)

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
        print(f"Retry {attempt+1}: Failed to fetch data. Status: {response.status_code}")
        time.sleep(delay)
    return None

def determine_export_from():
    """Determine the start date for data export."""
    return '2010-01-01' if FULL_IMPORT else (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

def classify_activity(activity_type):
    """Map activity types to standardized values."""
    activity_map = {
        'VirtualRun': 'RUN', 'Run': 'RUN',
        'VirtualRide': 'BIKE', 'Ride': 'BIKE',
        'Swim': 'SWIM', 'Yoga': 'YOGA',
        'Weight Training': 'STRENGTH'
    }
    return activity_map.get(activity_type, 'IGNORE')


def process_activity(activity, intervals_uid):
    """Process and store an activity in DynamoDB."""
    activity_type = classify_activity(activity['type'])
    if activity_type == 'IGNORE':
        return

    item = {
        'PK': f'USER#{intervals_uid}',
        'SK': f'ACTIVITY#{activity_type}#{datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S').strftime('%Y#%m#%d')}#{activity['id']}',
        'GSI1PK': f'{intervals_uid}#ACTIVITY',
        'GSI1SK': activity['start_date_local'],
        'id': activity['id'],
        'activity': activity_type,
        'name': activity.get('name'),
        'description': activity.get('description')
    }

    optional_fields = ['average_speed', 'max_speed', 'distance', 'moving_time', 'elapsed_time', 
                       'max_heartrate', 'average_heartrate', 'average_cadence', 'calories', 
                       'icu_hr_zone_times', 'icu_achievements', 'lengths', 'pool_length', 
                       'pace', 'icu_training_load', 'total_elevation_gain', 'gear']

    item.update({k: activity[k] for k in optional_fields if k in activity and activity[k] is not None})

    try:
        table.put_item(Item=item)
        process_personal_records(activity, item, intervals_uid)
        if activity.get('sub_type') == "RACE":
            process_race(item, intervals_uid)
    except ClientError as e:
        if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
            raise

def process_race(item, intervals_uid):
    race_item = item
    race_item['SK'] = f'RACE#{item['activity']}#{datetime.strptime(item['GSI1SK'], '%Y-%m-%dT%H:%M:%S').strftime('%Y#%m#%d')}#{item['name']}#{item['id']}'
    race_item['GSI1PK'] = f'{intervals_uid}#RACE'
    
    try:
        table.put_item(Item=race_item)
    except ClientError as e:
        if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
            raise

def process_personal_records(activity, item, intervals_uid):
    """Process personal records from an activity."""
    if 'icu_achievements' not in item:
        return

    pr_fields = ['distance', 'secs', 'pace', 'watts', 'message', 'value']
    for pr in item['icu_achievements']:
        pr_name = str(int(pr['distance'])) if pr['type'] == 'BEST_PACE' else pr['secs']
        pr_item = {
            'PK': item['PK'],
            'SK': f'PR#{item['activity']}#{pr['type']}#{pr_name}#{item['SK'].split('#')[-1]}',
            'GSI1PK': f'{intervals_uid}#PR',
            'GSI1SK': item['GSI1SK'],
        }
        pr_item.update({k: pr[k] for k in pr_fields if k in pr and pr[k] is not None})

        try:
            table.put_item(Item=pr_item)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                raise


def process_health_data(health_entries, intervals_uid):
    """Process and store health data in DynamoDB."""
    for entry in health_entries:
        item = {
            'PK': f'USER#{intervals_uid}',
            'SK': f'HEALTH#{entry['id'].replace('-', '#')}',
            'GSI1PK': f'{intervals_uid}#HEALTH',
            'GSI1SK': entry['id'],
        }

        fields = ['weight', 'restingHR', 'hrv', 'ctl', 'atl', 'sleepSecs', 'sleepScore',
                  'sleepQuality', 'soreness', 'fatigue', 'steps', 'rampRate']

        item.update({k: entry[k] for k in fields if k in entry and entry[k] is not None})

        if all(k in item for k in ('atl', 'ctl', 'rampRate')) and all(item[k] != 0 for k in ('atl', 'ctl', 'rampRate')):
            try:
                table.put_item(Item=item)
            except ClientError as e:
                if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                    raise
        else:
            print("Skipping entry with insufficient data.")


def main(event, context):
    """Main function to orchestrate data retrieval and processing."""
    intervals_api_key = get_ssm_param(f'/{PROJECT_NAME}/intervals/api_key')
    intervals_uid = get_ssm_param(f'/{PROJECT_NAME}/intervals/uid')

    if not intervals_api_key or not intervals_uid:
        print("Error retrieving API keys or user ID.")
        return

    export_from = determine_export_from()

    activities = fetch_data(f'{BASE_URL}{intervals_uid}/activities?oldest={export_from}', intervals_api_key)
    if activities:
        for activity in activities:
            process_activity(activity, intervals_uid)

    health_data = fetch_data(f'{BASE_URL}{intervals_uid}/wellness?oldest={export_from}', intervals_api_key)
    if health_data:
        process_health_data(health_data, intervals_uid)
