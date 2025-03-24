import os
import requests
import json
import time
import calendar
import boto3
import pandas as pd
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta

# Environment Variables
PROJECT_NAME = os.getenv('PROJECT_NAME')
AWS_SESSION_TOKEN = os.getenv('AWS_SESSION_TOKEN')
SSM_URL = 'http://localhost:2773/systemsmanager/parameters/get?withDecryption=true&name='
INTERVALS_UID_PARAM = f'/{PROJECT_NAME}/intervals/uid'
SNS_TOPIC = os.getenv('SNS_TOPIC')
NOTIFICATIONS_ENABLED = os.getenv('NOTIFICATIONS_ENABLED')

SNS_CLIENT = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.getenv('DYNAMODB_TABLE'))

def fetch_intervals_uid():
    """Fetch Intervals UID from AWS SSM Parameter Store with a retry mechanism. This is needed as it can take a little bit of time for the layer to be ready."""
    headers = {'X-Aws-Parameters-Secrets-Token': AWS_SESSION_TOKEN}
    for _ in range(5):
        response = requests.get(f'{SSM_URL}{INTERVALS_UID_PARAM}', headers=headers)
        if response.ok:
            return json.loads(response.text)['Parameter']['Value']
        time.sleep(0.1)
    raise Exception("Failed to fetch Intervals UID after multiple attempts.")

def get_date_ranges():
    """Calculate start and end dates for monthly or weekly comparisons."""
    now = datetime.now()
    
    if now.day == 1:  # Monthly case
        first_day_last_month = now.replace(day=1) - timedelta(days=1)
        start_date = first_day_last_month.replace(day=1).strftime('%Y-%m-%dT%H:%M:%S')
        end_date = first_day_last_month.strftime('%Y-%m-%dT%H:%M:%S')
        return start_date, end_date, None, None, 'monthly'

    if now.weekday() == 0:  # Weekly case (Monday)
        last_week_start = now - timedelta(days=now.weekday() + 7)
        last_week_end = last_week_start + timedelta(days=6)
        prev_week_start = last_week_start - timedelta(days=7)
        prev_week_end = last_week_end - timedelta(days=7)

        return (last_week_start.strftime('%Y-%m-%dT%H:%M:%S'), last_week_end.strftime('%Y-%m-%dT%H:%M:%S'),
                prev_week_start.strftime('%Y-%m-%dT%H:%M:%S'), prev_week_end.strftime('%Y-%m-%dT%H:%M:%S'), 'weekly')

    return None, None, None, None, None  # No relevant period

def query_table(index_name, partition_key, start_date, end_date):
    """Query DynamoDB table with given parameters."""
    response = table.query(
        IndexName=index_name,
        KeyConditionExpression=(
            Key('GSI1PK').eq(partition_key) & Key('GSI1SK').between(start_date, end_date)
        ),
    )
    return response.get('Items', [])

def crunch_activity_numbers(items):
    """Process activity stats using Pandas."""
    if not items:
        return {}

    df = pd.DataFrame(items)
    
    return {
        'total_time': df['elapsed_time'].sum(),
        'total_distance': df['distance'].sum(),
        'total_calories': df['calories'].sum(),
        'dist_per_activity': df.groupby('activity')['distance'].sum().div(1000).round(1).to_dict(),
        'num_activities': df['activity'].value_counts().to_dict(),
        'zones': {
            i + 1: {'time': t, 'percent': round((t / df['elapsed_time'].sum()) * 100) if t > 0 else 0}
            for i, t in enumerate(pd.DataFrame(df['icu_hr_zone_times'].to_list()).sum())
        }
    }

def crunch_health_numbers(items, compare_items):
    """Process health stats using Pandas."""
    if not items:
        return {}

    df_now = pd.DataFrame(items)
    if compare_items is not None:
        df_prev = pd.DataFrame(compare_items)
        return {
            'avg_steps': round(df_now['steps'].mean()),
            'avg_weight': round(df_now['weight'].mean(), 1),
            'avg_weight_diff': round(df_now['weight'].mean() - df_prev['weight'].mean(), 1),
            'avg_hr': round(df_now['restingHR'].mean(), 1),
            'avg_hr_diff': round(df_now['restingHR'].mean() - df_prev['restingHR'].mean(), 1),
            'avg_hrv': round(df_now['hrv'].mean(), 1)
        }
    else:
        return {
            'avg_steps': round(df_now['steps'].mean()),
            'avg_weight': round(df_now['weight'].mean(), 1),
            'avg_hr': round(df_now['restingHR'].mean(), 1),
            'avg_hrv': round(df_now['hrv'].mean(), 1)
        }
    
def process_personal_records(pr_items):
    """Processes personal records and structures them for notification."""
    if not pr_items:
        return None  # No PRs

    pr_summary = {}
    for pr in pr_items:
        activity_type = pr['SK'].split('#')[1]  # Extract activity type (RUN, SWIM, etc.)
        pr_type = pr['SK'].split('#')[2]  # Extract PR type (BEST_PACE, BEST_POWER, etc.)
        date_achieved = pr['GSI1SK'][:10]  # Extract only the YYYY-MM-DD part

        # Determine PR value (distance, pace, power)
        distance = float(pr.get('distance', 0))
        secs = float(pr.get('secs', 0))
        power = pr.get('power')  # Power PRs don't use pace

        formatted_pr = ''

        # Running PR handling
        if activity_type == 'RUN':
            if pr_type == 'BEST_PACE' and distance >= 1000:  
                pace_min_km = (secs / (distance / 1000)) / 60  # Convert to min/km
                formatted_pr = f'Best Pace: {pace_min_km:.2f} min/km ({distance / 1000:.1f}km) - {date_achieved}'
            elif pr_type == 'BEST_PACE':
                pace_min_km = (secs / distance) * 1000 / 60  # Convert to min/km
                formatted_pr = f'Best Pace: {pace_min_km:.2f} min/km ({distance}m) - {date_achieved}'
            elif pr_type == 'BEST_POWER':
                formatted_pr = f'Best Power: {power}W - {date_achieved}'

        # Swimming PR handling
        elif activity_type == 'SWIM':
            if pr_type == 'BEST_PACE':
                pace_min_100m = (secs / (distance / 100)) / 60  # Convert to min/100m
                formatted_pr = f'Best Pace: {pace_min_100m:.2f} min/100m ({distance}m) - {date_achieved}'
            elif pr_type == 'BEST_POWER':
                formatted_pr = f'Best Power: {power}W - {date_achieved}'

        # General power PRs (for cycling, rowing, etc.)
        elif pr_type == 'BEST_POWER':
            formatted_pr = f'Best Power: {power}W - {date_achieved}'

        # Add to summary
        if activity_type not in pr_summary:
            pr_summary[activity_type] = []
        
        pr_summary[activity_type].append(formatted_pr)

    return pr_summary

def notify(activity, health, pr_stats, period):
    """Format and send notification message."""
    if 'avg_weight_diff' in health:
        message = (
            f"<b>{period.title()} Health Stats:</b>\n\n"
            f"Your average weight was {health['avg_weight']}kg.\n"
            f"This is a difference of {health['avg_weight_diff']}kg from the previous period.\n"
            f"Your average steps were {health['avg_steps']}.\n\n"
            f"<b>{period.title()} Training Stats:</b>\n\n"
            f"Total time training: {timedelta(seconds=int(activity['total_time']))}\n"
            f"Total distance covered: {activity['total_distance'] / 1000:.1f}km\n"
            f"Total calories burned: {activity['total_calories']}\n\n"
            f"Number of activities:\n" +
            "\n".join(f"{act.title()}: {cnt}" for act, cnt in activity['num_activities'].items()) +
            "\n\nDistance per activity:\n" +
            "\n".join(f"{act.title()}: {dist:.2f}km" for act, dist in activity['dist_per_activity'].items())
        )
    else:
        message = (
            f"<b>{period.title()} Health Stats:</b>\n\n"
            f"Your average weight was {health['avg_weight']}kg.\n"
            f"Your average steps were {health['avg_steps']}.\n\n"
            f"<b>{period.title()} Training Stats:</b>\n\n"
            f"Total time training: {timedelta(seconds=int(activity['total_time']))}\n"
            f"Total distance covered: {activity['total_distance'] / 1000:.1f}km\n"
            f"Total calories burned: {activity['total_calories']}\n\n"
            f"Number of activities:\n" +
            "\n".join(f"{act.title()}: {cnt}" for act, cnt in activity['num_activities'].items()) +
            "\n\nDistance per activity:\n" +
            "\n".join(f"{act.title()}: {dist:.2f}km" for act, dist in activity['dist_per_activity'].items())
        )

    # Append PR data if available
    if pr_stats:
        message += f"\n\n<b>{period.title()} Personal Records:</b>\n"
        for activity, records in pr_stats.items():
            message += f"\n{activity.title()}:\n" + "\n".join(records)

    print(message)
    if NOTIFICATIONS_ENABLED:
        SNS_CLIENT.publish(TopicArn=SNS_TOPIC, Subject="Training Stats", Message=message)

def main(event, context):
    """Main function to fetch, process, and notify about activity and health data."""
    try:
        start_date, end_date, compare_start, compare_end, period = get_date_ranges()
        if not start_date:
            print("Neither the start of a week nor a month. Exiting.")
            return
        
        intervals_uid = fetch_intervals_uid()

        partition_key = f'{intervals_uid}#ACTIVITY'
        activity_items = query_table('GSI1', partition_key, start_date, end_date)
        activity_stats = crunch_activity_numbers(activity_items)

        partition_key = f'{intervals_uid}#HEALTH'
        health_items = query_table('GSI1', partition_key, start_date, end_date)
        if compare_start is None or compare_end is None:
            print("No data to compare to.")
            compare_items = None
        else:
            compare_items = query_table('GSI1', partition_key, compare_start, compare_end)
        health_stats = crunch_health_numbers(health_items, compare_items)

        # Fetch personal records (PRs)
        partition_key = f'{intervals_uid}#PR'
        pr_items = query_table('GSI1', partition_key, start_date, end_date)
        pr_stats = process_personal_records(pr_items)

        notify(activity_stats, health_stats, pr_stats, period)

    except Exception as e:
        print(f"Error: {e}")
