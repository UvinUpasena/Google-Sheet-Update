import os
import json
import pandas as pd
import re
import urllib3
import boto3
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

http = urllib3.PoolManager()

def lambda_handler(event, context):
    print("Lambda triggered by S3 event")

    s3_info = event['Records'][0]['s3']
    bucket_name = s3_info['bucket']['name']
    key = s3_info['object']['key']
    filename = key.split('/')[-1]

    print(f"Bucket: {bucket_name}, File: {filename}")

    s3 = boto3.client('s3')
    local_path = f"/tmp/{filename}"
    s3.download_file(bucket_name, key, local_path)

    match = re.search(r'rain_transactions_(\d{4}-\d{2}-\d{2})', filename)
    if not match:
        raise Exception("Cannot extract date from filename")
    report_date = match.group(1)
    print(f"Report Date: {report_date}")

    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(os.environ['GOOGLE_SHEET_ID']).worksheets()[3]

    df = pd.read_csv(local_path)
    df['authorizedAt'] = pd.to_datetime(df['authorizedAt'], errors='coerce')
    df['date'] = df['authorizedAt'].dt.strftime('%Y-%m-%d')

    declined_today = df[(df['spend_status'] == 'declined') & (df['date'] == report_date)]
    df_on_date = df[df['date'] == report_date]
    total_txns = len(df_on_date)
    approved_txns = len(df_on_date[df_on_date['spend_status'] == 'completed'])
    pending_txns = len(df_on_date[df_on_date['spend_status'] == 'pending'])
    declined_txns = len(df_on_date[df_on_date['spend_status'] == 'declined'])
    decline_percentage = (declined_txns / total_txns * 100) if total_txns > 0 else 0
    reason_counts = declined_today['declinedReason'].fillna('').str.strip().value_counts().to_dict()

    all_values = sheet.get_all_values()
    headers = all_values[0]
    reason_col_index = 0
    start_row = 2

    if report_date in headers:
        date_col_index = headers.index(report_date)
    else:
        avg_index = headers.index("AVG")
        insert_index = avg_index + 1
        sheet.insert_cols([[]], insert_index + 1)
        sheet.update_cell(1, insert_index + 1, report_date)
        all_values = sheet.get_all_values()
        headers = all_values[0]
        date_col_index = headers.index(report_date)

    success_count = 0
    unmatched = []
    def normalize(text):
        return re.sub(r'\W+', '', str(text)).strip().lower()

    for reason, count in reason_counts.items():
        normalized_reason = normalize(reason)
        matched = False
        for i, row in enumerate(all_values[start_row - 1:], start=start_row):
            sheet_reason = row[reason_col_index].strip() if len(row) > reason_col_index else ''
            if normalize(sheet_reason) == normalized_reason:
                sheet.update_cell(i, date_col_index + 1, count)
                success_count += 1
                matched = True
                break
        if not matched:
            unmatched.append((reason, count))

    summary_map = {
        "Total Transactions": total_txns,
        "Approved Transactions": approved_txns,
        "Pending Transactions": pending_txns,
        "Declined Transactions": declined_txns,
        "Total Declined %": f"{decline_percentage:.2f}%"
    }

    summary_label_col_index = 2
    for i, row in enumerate(all_values, start=1):
        if len(row) > summary_label_col_index:
            label = row[summary_label_col_index].strip()
            if label in summary_map:
                value = summary_map[label]
                sheet.update_cell(i, date_col_index + 1, value)

    # 9. Send Slack Notification
    slack_message = {
        'text': f'Decline report for `{report_date}` processed.\nUpdated {success_count} reasons.\n'
                + (f'Unmatched reasons: {len(unmatched)}' if unmatched else 'All matched.')
    }

    encoded_msg = json.dumps(slack_message).encode('utf-8')
    resp = http.request(
        'POST',
        os.environ['SLACK_WEBHOOK_URL'],
        body=encoded_msg,
        headers={'Content-Type': 'application/json'}
    )
    print(f"Slack notification sent. Status: {resp.status}")

    return {"statusCode": 200, "body": "Success"}
