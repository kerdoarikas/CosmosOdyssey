import requests
from flask import Flask, render_template, request, flash, redirect, jsonify
import csv
from datetime import datetime
import pytz
from flask_apscheduler import APScheduler


app = Flask(__name__)

# the secret key for the flash function
app.config['SECRET_KEY'] = '0000-000000-0000'

scheduler = APScheduler()  # Define APScheduler


# Initialize the scheduler
scheduler.init_app(app)
scheduler.start()

# list to store the last 15 pricelists
pricelists = []


@scheduler.task('cron', id='delete_expired_reservations', minute='*')
def delete_expired_reservations():
    api_response = requests.get(f'https://cosmos-odyssey.azurewebsites.net/api/v1.0/TravelPrices')
    data = api_response.json()

    # Store the last 15 pricelists in a list
    # Check if the list is empty or if the current pricelist has a newer validUntil field
    if not pricelists or data['validUntil'] > pricelists[-1]['validUntil']:
        # Append the current pricelist to the list
        pricelists.append(data)

    # Oldest pricelists validUntil
    old_valid_until = datetime.fromisoformat(pricelists[0]['validUntil'])
    old_valid_until_str = old_valid_until.strftime("%Y-%m-%d %H:%M:%S")
    old_valid_until = datetime.strptime(old_valid_until_str, "%Y-%m-%d %H:%M:%S")  # Timezone UTC

    # If the list has more than 15 items, remove the oldest item
    if len(pricelists) > 15:
        # Remove reservations where reservation timestamp is later than oldest pricelist validUntil
        # Read the reservations from the file
        reservations = []
        with open('reservations.csv', 'r') as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                reservations.append(row)

        # Delete expired reservations
        for reservation in reservations:
            reservation_timestamp = reservation[8]
            res_tstmp_dt = datetime.strptime(reservation_timestamp, '%Y-%m-%d %H:%M:%S')
            if res_tstmp_dt < old_valid_until:
                reservations.remove(reservation)

        # Write the updated reservations to the file
        with open('reservations.csv', 'w', newline='') as csv_file:
            writer = csv.writer(csv_file)
            for reservation in reservations:
                writer.writerow(reservation)
        # Delete oldest pricelist
        del pricelists[0]


@app.route('/')
def index():
    planets = ['Mercury', 'Venus', 'Earth', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune']
    return render_template('index.html', planets=planets)


@app.route('/get_to_options', methods=['POST'])
def get_to_options():
    api_response = requests.get(f'https://cosmos-odyssey.azurewebsites.net/api/v1.0/TravelPrices')
    data = api_response.json()
    # getting the "from" location from the request
    from_location = request.json['from']

    # filtering available "to" locations based on the "from" location
    to_options = []
    for route in data['legs']:
        if route['routeInfo']['from']['name'] == from_location:
            to_options.append(route['routeInfo']['to']['name'])

    # return the filtered "to" locations as a JSON response
    return jsonify({'to_options': to_options})


@app.route('/search', methods=['POST'])
def search():
    planets = ['Mercury', 'Venus', 'Earth', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune']
    from_planet = request.form['from']
    to_planet = request.form['to']

    api_response = requests.get(f'https://cosmos-odyssey.azurewebsites.net/api/v1.0/TravelPrices')
    data = api_response.json()

    routes = []  # initialize routes list
    valid_until = ''  # set default value for valid_until
    for route in data['legs']:
        if route['routeInfo']['from']['name'] == from_planet and route['routeInfo']['to']['name'] == to_planet:
            client_timezone = request.headers.get('X-Timezone')
            if client_timezone:
                client_timezone = pytz.timezone(client_timezone)
            else:
                # Set a default timezone
                client_timezone = pytz.timezone('Europe/Tallinn')

            valid_until = datetime.fromisoformat(data['validUntil'])
            valid_until = valid_until.astimezone(client_timezone)
            valid_until_str = valid_until.strftime("%Y-%m-%d %H:%M:%S")
            valid_until = datetime.strptime(valid_until_str, "%Y-%m-%d %H:%M:%S")
            distance = route['routeInfo']['distance']
            for company in route['providers']:
                comp_name = company['company']['name']
                price = company['price']
                flight_start_is = datetime.fromisoformat(company['flightStart'])
                flight_start_is = flight_start_is.astimezone(client_timezone)
                flight_start = flight_start_is.strftime('%Y-%m-%d %H:%M:%S')
                flight_end_is = datetime.fromisoformat(company['flightEnd'])
                flight_end_is = flight_end_is.astimezone(client_timezone)
                flight_end = flight_end_is.strftime('%Y-%m-%d %H:%M:%S')
                travel_time = flight_end_is - flight_start_is

                routes.append({
                    'from': from_planet,
                    'to': to_planet,
                    'company': comp_name,
                    'price': price,
                    'flight_start': flight_start,
                    'flight_end': flight_end,
                    'travel_time': travel_time,
                    'distance': distance
                })
    # check if there are no routes found
    if not routes:
        flash("There are no providers for this route!", "error")

    return render_template('index.html', routes=routes, valid_until=valid_until, planets=planets)


@app.route('/reserve', methods=['POST'])
def reserve():
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
    # get the form data
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    route_from = request.form['route_from']
    route_to = request.form['route_to']
    price = request.form['price']
    company = request.form['company']
    distance = request.form['distance']
    flight_start = request.form['flight_start']

    valid_until_str = request.form['valid_until']
    valid_until = datetime.strptime(valid_until_str, "%Y-%m-%d %H:%M:%S")
    reservation_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not first_name.strip() or not last_name.strip():
        flash("Reservation canceled, first- or lastname not valid!", "error")
        return redirect('/')

    elif now > valid_until:
        flash("Reservation canceled, pricelist expired. Please try again.", "error")
        return redirect('/')
    else:
        # write the data to a CSV file
        with open('reservations.csv', 'a', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow([first_name, last_name, route_from, route_to,
                             price, company, distance, flight_start, reservation_timestamp])

        flash("Your reservation has been made successfully!", "success")
        # redirect to the home page
        return redirect('/')


@app.route('/view_reservations', methods=['GET', 'PUT', 'POST', 'DELETE'])
def view_reservations():
    # Show reservations
    if request.method == 'POST':
        # Get the form data
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        # Search the reservations.csv file for reservations made by the user
        reservations = []
        if first_name != 'all' and last_name != 'reservations':
            with open('reservations.csv', 'r') as csv_file:
                reader = csv.reader(csv_file)
                for row in reader:
                    if row[0] == first_name and row[1] == last_name:
                        reservations.append({
                            'first_name': row[0],
                            'last_name': row[1],
                            'route_from': row[2],
                            'route_to': row[3],
                            'price': row[4],
                            'company': row[5],
                            'distance': row[6]
                        })
            # Render the view_reservations template with the reservations data
            return render_template('view_reservations.html', reservations=reservations, first_name=first_name,
                                   last_name=last_name)
        else:
            with open('reservations.csv', 'r') as csv_file:
                reader = csv.reader(csv_file)
                for row in reader:
                    reservations.append({
                        'first_name': row[0],
                        'last_name': row[1],
                        'route_from': row[2],
                        'route_to': row[3],
                        'price': row[4],
                        'company': row[5],
                        'distance': row[6],
                    })
            # Render the view_reservations template with the reservations data
            return render_template('view_reservations.html', reservations=reservations, first_name=first_name,
                                   last_name=last_name)
    # Delete reservation
    elif request.method == 'DELETE':
        # get the first and last name from the query parameters
        first_name = request.args.get('first_name')
        last_name = request.args.get('last_name')

        # open the CSV file in read mode
        with open('reservations.csv', 'r', newline='') as csv_file:
            # read the rows of the CSV file
            rows = csv.reader(csv_file)
            # store the rows of the CSV file in a list
            reservations = list(rows)

            # find the reservation with the given first and last name
            for i, reservation in enumerate(reservations):
                if reservation[0] == first_name and reservation[1] == last_name:
                    # delete the reservation from the list
                    del reservations[i]
                    break

        # open the CSV file in write mode
        with open('reservations.csv', 'w', newline='') as csv_file:
            # write the updated list of reservations to the CSV file
            writer = csv.writer(csv_file)
            for reservation in reservations:
                writer.writerow(reservation)

        return redirect("/view_reservations")
    # Update reservation
    elif request.method == 'PUT':
        # get the reservation details from the query parameters
        first_name = request.args.get('first_name')
        last_name = request.args.get('last_name')
        new_first_name = request.args.get('new_first_name')
        new_last_name = request.args.get('new_last_name')

        # open the CSV file in read mode
        with open('reservations.csv', 'r', newline='') as csv_file:
            # read the rows of the CSV file
            rows = csv.reader(csv_file)
            # store the rows of the CSV file in a list
            reservations = list(rows)

            # find the reservation with the given first and last name
            for i, reservation in enumerate(reservations):
                if reservation[0] == first_name and reservation[1] == last_name:
                    # update the first and last name of the reservation
                    reservation[0] = new_first_name
                    reservation[1] = new_last_name
                    break

        # open the CSV file in write mode
        with open('reservations.csv', 'w', newline='') as csv_file:
            # write the updated list of reservations to the CSV file
            writer = csv.writer(csv_file)
            for reservation in reservations:
                writer.writerow(reservation)

        # Return a JSON object indicating that the reservation has been updated successfully
        flash("Your reservation has been updated successfully!", "success")
        return redirect('/view_reservations')

    else:
        # get the search criteria from the request form
        first_name = request.args.get('first_name')
        last_name = request.args.get('last_name')

        if first_name is None or last_name is None:
            return render_template('view_reservations.html', message='Invalid search criteria')

        # open the CSV file in read mode
        with open('reservations.csv', 'r', newline='') as csv_file:
            # read the rows of the CSV file
            rows = csv.reader(csv_file)
            # store the rows of the CSV file in a list
            reservations = list(rows)
            # filter the reservations based on the search criteria
            filtered_reservations = []
            for reservation in reservations:
                if first_name.lower() in reservation[0].lower() and last_name.lower() in reservation[1].lower():
                    filtered_reservations.append(reservation)

            if not filtered_reservations:
                flash("No reservations found!", "error")
                return render_template('view_reservations.html')
            else:
                return render_template('view_reservations.html', reservations=filtered_reservations)


if __name__ == '__main__':
    app.run()
