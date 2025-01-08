from flask import Flask, request, render_template, redirect, url_for
import pandas as pd
from openpyxl import load_workbook, Workbook
import os
import flask_lambda

app = Flask(__name__)

# Directories to store files
METADATA_FOLDER = "metadata"
METADATA_REPORTS_FOLDER = "metadata_reports"

os.makedirs(METADATA_FOLDER, exist_ok=True)
os.makedirs(METADATA_REPORTS_FOLDER, exist_ok=True)

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

    # Save the uploaded file in the metadata folder
    input_file_path = os.path.join(METADATA_FOLDER, file.filename)
    file.save(input_file_path)

    # Extract station name from file name (assuming file name format includes station name)
    station_name = os.path.splitext(file.filename)[0]
    report_file_path = os.path.join(METADATA_REPORTS_FOLDER, f"{station_name}_Metadata_Report.xlsx")

    # Generate or update the station's metadata report
    try:
        generate_availability_report(input_file_path, report_file_path, station_name)
        # Redirect to the success page
        return redirect(url_for('report_generated', station_name=station_name))
    except Exception as e:
        return f"Error generating the report: {e}", 500

@app.route('/report_generated/<station_name>')
def report_generated(station_name):
    return f"Report successfully generated for station: {station_name}. You can find it in the {METADATA_REPORTS_FOLDER} folder."

def generate_availability_report(input_file, report_file, station_name):
    # Step 1: Read the CSV input file
    df = pd.read_csv(input_file)

    # Ensure 'Date' column exists
    if 'Date' not in df.columns:
        raise ValueError("The input file must contain a 'Date' column.")

    # Process 'Date' column
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    if df['Date'].isna().any():
        raise ValueError("Some 'Date' values are invalid.")

    # Extract year and month
    df['Year'] = df['Date'].dt.year
    df['Month'] = df['Date'].dt.strftime('%b').str.upper()

    # Check existing report file
    if os.path.exists(report_file):
        wb = load_workbook(report_file)
        ws = wb.active

        # Extract existing year-month combinations from the report
        existing_months = {(row[0].value, row[1].value) for row in ws.iter_rows(min_row=2, max_col=2)}
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Metadata Report"

        # Write headers for new file
        headers = ["Year", "Month", "Data Availability", "Data Missing", "Station Name"] + [
            "Outdoor Temperature (°C)", "Feels Like (°C)", "Dew Point (°C)", "Wind Speed (km/hr)", "Wind Gust (km/hr)",
            "Max Daily Gust (km/hr)", "Wind Direction (°)", "Rain Rate(mm/hr)", "Event Rain (mm)", "Daily Rain (mm)",
            "Weekly Rain (mm)", "Monthly Rain (mm)", "Yearly Rain (mm)", "Relative Pressure (hPa)", "Humidity (%)",
            "Ultra-Violet Radiation Index", "Solar Radiation (W/m^2)", "Indoor Temperature (°C)", "Indoor Humidity (%)",
            "PM2.5 Outdoor (µg/m³)", "PM2.5 Outdoor 24 Hour Average (µg/m³)", "Indoor Battery", "Indoor Feels Like (°C)",
            "Indoor Dew Point (°C)", "Absolute Pressure (hPa)", "Outdoor Battery", "Avg Wind Direction (10 mins) (°)",
            "Avg Wind Speed (10 mins) (km/hr)", "Total Rain", "CO2 Battery", "PM 2.5 (µg/m³)"
        ]
        ws.append(headers)
        existing_months = set()

    # Step 2: Process the input data for each month
    grouped = df.groupby(['Year', 'Month'])
    for (year, month), month_data in grouped:
        if (year, month) in existing_months:
            continue  # Skip if data for this year-month already exists

        # Check data availability
        available_dates = month_data['Date'].dt.strftime('%d/%m').tolist()
        data_availability = f"{available_dates[0]}-{available_dates[-1]}"

        # Find missing dates in the month
        month_number = month_data['Date'].dt.month.iloc[0]
        all_dates = pd.date_range(
            start=f"{year}-{month_number:02d}-01",
            end=f"{year}-{month_number:02d}-{month_data['Date'].dt.days_in_month.iloc[0]}"
        )
        missing_dates = [d.strftime('%d/%m') for d in all_dates if d not in month_data['Date'].tolist()]
        data_missing = ", ".join(missing_dates) if missing_dates else "-"

        # Check variable availability
        expected_variables = [
            "Outdoor Temperature (°C)", "Feels Like (°C)", "Dew Point (°C)", "Wind Speed (km/hr)", "Wind Gust (km/hr)",
            "Max Daily Gust (km/hr)", "Wind Direction (°)", "Rain Rate(mm/hr)", "Event Rain (mm)", "Daily Rain (mm)",
            "Weekly Rain (mm)", "Monthly Rain (mm)", "Yearly Rain (mm)", "Relative Pressure (hPa)", "Humidity (%)",
            "Ultra-Violet Radiation Index", "Solar Radiation (W/m^2)", "Indoor Temperature (°C)", "Indoor Humidity (%)",
            "PM2.5 Outdoor (µg/m³)", "PM2.5 Outdoor 24 Hour Average (µg/m³)", "Indoor Battery", "Indoor Feels Like (°C)",
            "Indoor Dew Point (°C)", "Absolute Pressure (hPa)", "Outdoor Battery", "Avg Wind Direction (10 mins) (°)",
            "Avg Wind Speed (10 mins) (km/hr)", "Total Rain", "CO2 Battery", "PM 2.5 (µg/m³)"
        ]
        available_variables = [col for col in expected_variables if col in month_data.columns]

        # Prepare the row for output
        row = [year, month, data_availability, data_missing, station_name]
        for variable in expected_variables:
            row.append("✓" if variable in available_variables else "-")

        # Append the row to the worksheet
        ws.append(row)

    # Save the updated workbook
    wb.save(report_file)

# Set up Flask app for AWS Lambda
app = flask_lambda.Flask(app)

if __name__ == '__main__':
    app.run(debug=True)
