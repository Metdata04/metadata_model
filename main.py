from flask import Flask, request, render_template, redirect, url_for
import pandas as pd
import os
import requests
import base64

app = Flask(__name__)

# Directories to store files temporarily
METADATA_FOLDER = "/tmp/metadata"
METADATA_REPORTS_FOLDER = "/tmp/metadata_reports"

os.makedirs(METADATA_FOLDER, exist_ok=True)
os.makedirs(METADATA_REPORTS_FOLDER, exist_ok=True)

# GitHub repository details
GITHUB_API_URL = "https://api.github.com"
REPO_OWNER = "Metdata04"  # GitHub username
REPO_NAME = "metadata_model"  # Repository name
BRANCH_NAME = "main"  # Branch name
GITHUB_TOKEN = os.getenv("Metadata_token")  # GitHub personal access token
if not GITHUB_TOKEN:
    raise ValueError("GitHub token is not set in environment variables.")

def upload_file_to_github(file, file_name, commit_message="Add new report"):
    url = f"{GITHUB_API_URL}/repos/{REPO_OWNER}/{REPO_NAME}/contents/{file_name}"

    # Check if the file exists
    response = requests.get(
        url,
        headers={"Authorization": f"token {GITHUB_TOKEN}"}
    )

    sha = None  # Default to None if file doesn't exist
    if response.status_code == 200:
        # File exists, get the sha of the current file
        sha = response.json().get('sha')

    # Ensure file pointer is at the start
    file.seek(0)

    # Encode the file to base64
    encoded_file = base64.b64encode(file.read()).decode("utf-8")

    # Prepare the data for upload (either creating or updating the file)
    data = {
        "message": commit_message,
        "content": encoded_file,
        "branch": BRANCH_NAME
    }

    # If sha is found, it means we are updating an existing file
    if sha:
        data['sha'] = sha

    # Perform the PUT request to upload or update the file
    response = requests.put(
        url,
        headers={"Authorization": f"token {GITHUB_TOKEN}"},
        json=data
    )

    # Check the response status
    if response.status_code in (200, 201):
        return f"File {file_name} uploaded/updated successfully."
    else:
        raise Exception(f"Failed to upload file: {response.status_code} - {response.text}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No file part", 400

    file = request.files['file']

    if file.filename == '':
        return "No selected file", 400

    # Get station name from the file name (e.g., 'station_name.csv')
    station_name = os.path.splitext(file.filename)[0]

    # Save the uploaded file temporarily to process it
    input_file_path = os.path.join(METADATA_FOLDER, file.filename)
    file.save(input_file_path)

    # Read the file to get the first date (assumed to be the first row in the 'Date' column)
    df = pd.read_csv(input_file_path)
    if 'Date' not in df.columns:
        return "The file must contain a 'Date' column.", 400

    # Extract the year and month from the first date entry
    first_date = pd.to_datetime(df['Date'].iloc[0])
    year_month = first_date.strftime('%Y-%m')

    # Create the full path to simulate folder structure in the repository
    file_name_in_github = f"{station_name}/{year_month}.csv"

    try:
        # Upload the file to GitHub with the new folder and name
        upload_result = upload_file_to_github(file, file_name_in_github, f"Add/update file for {station_name} for {year_month}")
        print(upload_result)
        
        # Generate the availability report
        report_file_path = os.path.join(METADATA_REPORTS_FOLDER, f"{station_name}_Metadata_Report.csv")
        generate_availability_report(input_file_path, report_file_path, station_name)

        # Upload the report to the "metadata_reports" folder in the repository
        report_file_name_in_github = f"metadata_reports/{station_name}_Metadata_Report.csv"
        with open(report_file_path, 'rb') as report_file:
            upload_result = upload_file_to_github(report_file, report_file_name_in_github, f"Add/update metadata report for {station_name}")
        print(upload_result)

        return redirect(url_for('report_generated', station_name=station_name))
    except Exception as e:
        return f"Error generating the report: {e}", 500

@app.route('/report_generated/<station_name>')
def report_generated(station_name):
    return f"Report successfully generated for station: {station_name}. You can find it in the GitHub repository."

def generate_availability_report(input_file, report_file, station_name):
    # Read the input CSV file
    df = pd.read_csv(input_file)

    # Ensure the 'Date' column exists and is valid
    if 'Date' not in df.columns:
        raise ValueError("The input file must contain a 'Date' column.")

    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    if df['Date'].isna().any():
        raise ValueError("Some 'Date' values in the 'Date' column are invalid.")

    # Create "Year" and "Month" columns for grouping
    df['Year'] = df['Date'].dt.year
    df['Month'] = df['Date'].dt.strftime('%b').str.upper()

    # Initialize the report DataFrame
    headers = ["Year", "Month", "Data Availability", "Data Missing", "Station Name"] + [
        "Outdoor Temperature (°C)", "Feels Like (°C)", "Dew Point (°C)", "Wind Speed (km/hr)", "Wind Gust (km/hr)",
        "Max Daily Gust (km/hr)", "Wind Direction (°)", "Rain Rate (mm/hr)", "Event Rain (mm)", "Daily Rain (mm)",
        "Weekly Rain (mm)", "Monthly Rain (mm)", "Yearly Rain (mm)", "Relative Pressure (hPa)", "Humidity (%)",
        "Ultra-Violet Radiation Index", "Solar Radiation (W/m^2)", "Indoor Temperature (°C)", "Indoor Humidity (%)",
        "PM2.5 Outdoor (μg/m³)", "PM2.5 Outdoor 24 Hour Average (μg/m³)", "Indoor Battery", "Indoor Feels Like (°C)",
        "Indoor Dew Point (°C)", "Absolute Pressure (hPa)", "Outdoor Battery", "Avg Wind Direction (10 mins) (°)",
        "Avg Wind Speed (10 mins) (km/hr)", "Total Rain (mm)", "CO2 battery", "PM2.5 Outdoor", "PM2.5 Outdoor 24 Hour Average", "PM2.5 Outdoor Battery"
    ]

    report_data = []

    # Group data by Year and Month
    grouped = df.groupby(['Year', 'Month'])
    for (year, month), month_data in grouped:
        # Calculate data availability and missing data
        available_dates = month_data['Date'].dt.strftime('%d/%m').tolist()
        data_availability = f"{available_dates[0]}-{available_dates[-1]}" if available_dates else "-"

        # Create the full month for comparison to get missing dates
        month_number = month_data['Date'].dt.month.iloc[0]
        all_dates = pd.date_range(
            start=f"{year}-{month_number:02d}-01",
            end=f"{year}-{month_number:02d}-{month_data['Date'].dt.days_in_month.iloc[0]}"
        )

        all_dates_set = set(all_dates.date)
        available_dates_set = set(month_data['Date'].dt.date)
        missing_dates = all_dates_set - available_dates_set
        formatted_missing_dates = [d.strftime('%d/%m') for d in sorted(missing_dates)]
        data_missing = ", ".join(formatted_missing_dates) if formatted_missing_dates else "-"

        # Filter the columns for available variables for this station
        expected_variables = headers[5:]
        available_variables = [col for col in expected_variables if col in month_data.columns]

        row = [year, month, data_availability, data_missing, station_name]

        # Check each variable for availability
        for variable in expected_variables:
            if variable in available_variables:
                # Check for full or partial availability
                available_data = month_data[variable].notna() & (month_data[variable] != "")
                total_rows = len(month_data)
                available_count = available_data.sum()

                if available_count == total_rows:
                    row.append("✓")  # Full availability
                elif available_count == 0:
                    row.append("-")  # Full absence
                else:
                    # Partial availability
                    availability_percentage = (available_count / total_rows) * 100
                    row.append(f"{availability_percentage:.2f}%")  # Display the percentage
            else:
                row.append("-")  # Variable is not present in the data

        report_data.append(row)

    # Convert the report data into a DataFrame
    report_df = pd.DataFrame(report_data, columns=headers)

    # Save the report as a CSV file
    report_df.to_csv(report_file, index=False)

if __name__ == '__main__':
    app.run(debug=True)
