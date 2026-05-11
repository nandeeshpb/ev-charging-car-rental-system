import os
import random
from datetime import datetime
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import Flask, flash, redirect, render_template, request, session, url_for
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "uniccars-dev-secret-key")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2500)
mongo_db = mongo_client["client"]

users_col = mongo_db["users"]
cars_col = mongo_db["cars"]
stations_col = mongo_db["stations"]
bookings_col = mongo_db["bookings"]


def ensure_database():
    users_col.create_index([("email", ASCENDING)], unique=True)
    cars_col.create_index([("name", ASCENDING)])
    stations_col.create_index([("name", ASCENDING)])
    bookings_col.create_index([("user.email", ASCENDING), ("created_at", DESCENDING)])


def mongo_ready():
    try:
        mongo_client.admin.command("ping")
        return True
    except ServerSelectionTimeoutError:
        return False


def generate_otp():
    return f"{random.randint(100000, 999999)}"


def oid(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def format_docs(cursor):
    docs = list(cursor)
    for doc in docs:
        doc["_id_str"] = str(doc["_id"])
    return docs


def parse_future_date(value):
    try:
        selected = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None, "Please select a valid date."

    if selected < datetime.today().date():
        return None, "Booking date cannot be in the past."
    return selected.isoformat(), None


def current_user():
    if "user" not in session:
        return None
    return session["user"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            flash("Please login to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user", {}).get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    return {"current_user": current_user()}


def seed_dummy_data():
    if not mongo_ready():
        return

    ensure_database()

    if users_col.count_documents({"email": "admin@uniccars.com"}) == 0:
        users_col.insert_one(
            {
                "name": "Admin",
                "email": "admin@uniccars.com",
                "password": generate_password_hash("admin123"),
                "role": "admin",
                "verified": True,
                "created_at": datetime.utcnow(),
            }
        )

    if cars_col.count_documents({}) == 0:
        cars_col.insert_many(
            [
                {
                    "name": "Tesla Model 3",
                    "type": "Electric",
                    "price": 4500,
                    "image": "https://images.unsplash.com/photo-1560958089-b8a1929cea89?auto=format&fit=crop&w=1200&q=80",
                },
                {
                    "name": "Hyundai Kona EV",
                    "type": "Electric",
                    "price": 3200,
                    "image": "https://images.unsplash.com/photo-1619767886558-efdc259cde1a?auto=format&fit=crop&w=1200&q=80",
                },
                {
                    "name": "Mahindra XUV700",
                    "type": "SUV",
                    "price": 2800,
                    "image": "https://images.unsplash.com/photo-1600706432502-77a0e2e327aa?auto=format&fit=crop&w=1200&q=80",
                },
                {
                    "name": "Honda City",
                    "type": "Sedan",
                    "price": 1900,
                    "image": "https://images.unsplash.com/photo-1494976388531-d1058494cdd8?auto=format&fit=crop&w=1200&q=80",
                },
            ]
        )

    if stations_col.count_documents({}) == 0:
        stations_col.insert_many(
            [
                {
                    "name": "GreenVolt Central",
                    "location": "Bengaluru",
                    "type": "Fast",
                    "availability": 8,
                    "coordinates": {"lat": 12.9716, "lng": 77.5946},
                },
                {
                    "name": "EcoCharge Hub",
                    "location": "Mumbai",
                    "type": "Normal",
                    "availability": 12,
                    "coordinates": {"lat": 19.0760, "lng": 72.8777},
                },
                {
                    "name": "Rapid Plug Point",
                    "location": "Delhi",
                    "type": "Fast",
                    "availability": 5,
                    "coordinates": {"lat": 28.6139, "lng": 77.2090},
                },
                {
                    "name": "Urban EV Dock",
                    "location": "Chennai",
                    "type": "Normal",
                    "availability": 9,
                    "coordinates": {"lat": 13.0827, "lng": 80.2707},
                },
            ]
        )


@app.route("/")
def index():
    if not mongo_ready():
        flash("MongoDB is not running. Start MongoDB Compass/local server and reload.", "error")
        return render_template("index.html", cars=[], stations=[])

    cars = format_docs(cars_col.find().limit(3))
    stations = format_docs(stations_col.find().limit(4))
    return render_template("index.html", cars=cars, stations=stations)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not mongo_ready():
            flash("MongoDB connection failed. Start MongoDB and try again.", "error")
            return render_template("register.html", verify_mode=False)

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Name, email, and password are required.", "error")
        elif len(name) < 3:
            flash("Name must be at least 3 characters.", "error")
        elif "@" not in email or "." not in email:
            flash("Enter a valid email address.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif users_col.find_one({"email": email, "verified": True}):
            flash("Email is already registered.", "error")
        else:
            otp = generate_otp()
            users_col.update_one(
                {"email": email},
                {
                    "$set": {
                        "name": name,
                        "email": email,
                        "password": generate_password_hash(password),
                        "role": "user",
                        "verified": False,
                        "otp": otp,
                        "otp_created_at": datetime.utcnow(),
                    }
                },
                upsert=True,
            )
            print(f"UNICCARS verification OTP for {email}: {otp}")
            flash(f"Verification OTP generated. Demo OTP: {otp}", "success")
            return redirect(url_for("verify_email", email=email))

    return render_template("register.html", verify_mode=False)


@app.route("/verify/<email>", methods=["GET", "POST"])
def verify_email(email):
    email = email.strip().lower()
    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        user = users_col.find_one({"email": email})

        if not user:
            flash("No registration found for this email.", "error")
            return redirect(url_for("register"))
        if user.get("verified"):
            flash("Email already verified. Please login.", "success")
            return redirect(url_for("login"))
        if otp != user.get("otp"):
            flash("Invalid OTP. Please check and try again.", "error")
        else:
            users_col.update_one(
                {"email": email},
                {"$set": {"verified": True}, "$unset": {"otp": "", "otp_created_at": ""}},
            )
            flash("Email verified successfully. You can login now.", "success")
            return redirect(url_for("login"))

    return render_template("register.html", verify_mode=True, email=email)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not mongo_ready():
            flash("MongoDB connection failed. Start MongoDB and try again.", "error")
            return render_template("login.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = users_col.find_one({"email": email})

        if not user or not check_password_hash(user.get("password", ""), password):
            flash("Invalid email or password.", "error")
        elif not user.get("verified"):
            flash("Please verify your email before login.", "error")
            return redirect(url_for("verify_email", email=email))
        else:
            session.clear()
            session["user"] = {
                "id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
            }
            flash(f"Welcome to UNICCARS, {user['name']}.", "success")
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    cars = format_docs(cars_col.find().sort("name", ASCENDING))
    stations = format_docs(stations_col.find().sort("name", ASCENDING))
    bookings = format_docs(
        bookings_col.find({"user.email": session["user"]["email"]}).sort("created_at", DESCENDING)
    )
    return render_template("dashboard.html", cars=cars, stations=stations, bookings=bookings)


@app.route("/book", methods=["GET", "POST"])
@login_required
def book_slot():
    cars = format_docs(cars_col.find().sort("name", ASCENDING))
    stations = format_docs(stations_col.find().sort("name", ASCENDING))

    if request.method == "POST":
        car_id = oid(request.form.get("car_id"))
        station_id = oid(request.form.get("station_id"))
        booking_date, date_error = parse_future_date(request.form.get("date", ""))
        car = cars_col.find_one({"_id": car_id}) if car_id else None
        station = stations_col.find_one({"_id": station_id}) if station_id else None

        if not car:
            flash("Please select a valid car.", "error")
        elif not station:
            flash("Please select a valid station.", "error")
        elif date_error:
            flash(date_error, "error")
        elif int(station.get("availability", 0)) <= 0:
            flash("Selected station has no available slots.", "error")
        else:
            booking = {
                "user": {
                    "name": session["user"]["name"],
                    "email": session["user"]["email"],
                },
                "car": {"id": str(car["_id"]), "name": car["name"], "type": car["type"]},
                "station": {
                    "id": str(station["_id"]),
                    "name": station["name"],
                    "location": station["location"],
                    "type": station["type"],
                },
                "date": booking_date,
                "created_at": datetime.utcnow(),
            }
            bookings_col.insert_one(booking)
            stations_col.update_one({"_id": station["_id"]}, {"$inc": {"availability": -1}})
            flash("Booking confirmed successfully.", "success")
            return redirect(url_for("dashboard"))

    return render_template("book_slot.html", cars=cars, stations=stations)


@app.route("/admin", methods=["GET", "POST"])
@login_required
@admin_required
def admin_dashboard():
    if request.method == "POST":
        action = request.form.get("action")

        try:
            if action == "add_car":
                add_car_from_form()
            elif action == "add_station":
                add_station_from_form()
            else:
                flash("Invalid admin action.", "error")
        except PyMongoError:
            flash("Database operation failed. Please try again.", "error")

        return redirect(url_for("admin_dashboard"))

    cars = format_docs(cars_col.find().sort("name", ASCENDING))
    stations = format_docs(stations_col.find().sort("name", ASCENDING))
    users = format_docs(users_col.find({}, {"password": 0, "otp": 0}).sort("name", ASCENDING))
    bookings = format_docs(bookings_col.find().sort("created_at", DESCENDING))
    return render_template(
        "admin_dashboard.html",
        cars=cars,
        stations=stations,
        users=users,
        bookings=bookings,
    )


def add_car_from_form():
    name = request.form.get("name", "").strip()
    car_type = request.form.get("type", "").strip()
    image = request.form.get("image", "").strip()
    price = request.form.get("price", type=float)

    if not name or car_type not in {"SUV", "Sedan", "Electric"}:
        flash("Enter a valid car name and type.", "error")
    elif price is None or price <= 0:
        flash("Car price must be greater than zero.", "error")
    else:
        cars_col.insert_one({"name": name, "type": car_type, "price": price, "image": image})
        flash("Car added successfully.", "success")


def add_station_from_form():
    name = request.form.get("name", "").strip()
    location = request.form.get("location", "").strip()
    station_type = request.form.get("type", "").strip()
    availability = request.form.get("availability", type=int)
    lat = request.form.get("lat", type=float)
    lng = request.form.get("lng", type=float)

    if not name or not location or station_type not in {"Fast", "Normal"}:
        flash("Enter valid station name, location, and type.", "error")
    elif availability is None or availability < 0:
        flash("Availability must be zero or more.", "error")
    elif lat is None or lng is None:
        flash("Latitude and longitude are required.", "error")
    else:
        stations_col.insert_one(
            {
                "name": name,
                "location": location,
                "type": station_type,
                "availability": availability,
                "coordinates": {"lat": lat, "lng": lng},
            }
        )
        flash("Station added successfully.", "success")


@app.route("/admin/car/<car_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_car(car_id):
    car_object_id = oid(car_id)
    if not car_object_id:
        flash("Invalid car id.", "error")
        return redirect(url_for("admin_dashboard"))

    name = request.form.get("name", "").strip()
    car_type = request.form.get("type", "").strip()
    image = request.form.get("image", "").strip()
    price = request.form.get("price", type=float)

    if not name or car_type not in {"SUV", "Sedan", "Electric"}:
        flash("Enter valid car details.", "error")
    elif price is None or price <= 0:
        flash("Car price must be greater than zero.", "error")
    else:
        cars_col.update_one(
            {"_id": car_object_id},
            {"$set": {"name": name, "type": car_type, "price": price, "image": image}},
        )
        flash("Car updated successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/car/<car_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_car(car_id):
    car_object_id = oid(car_id)
    if not car_object_id:
        flash("Invalid car id.", "error")
    else:
        cars_col.delete_one({"_id": car_object_id})
        flash("Car deleted successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/station/<station_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_station(station_id):
    station_object_id = oid(station_id)
    if not station_object_id:
        flash("Invalid station id.", "error")
        return redirect(url_for("admin_dashboard"))

    name = request.form.get("name", "").strip()
    location = request.form.get("location", "").strip()
    station_type = request.form.get("type", "").strip()
    availability = request.form.get("availability", type=int)
    lat = request.form.get("lat", type=float)
    lng = request.form.get("lng", type=float)

    if not name or not location or station_type not in {"Fast", "Normal"}:
        flash("Enter valid station details.", "error")
    elif availability is None or availability < 0:
        flash("Availability must be zero or more.", "error")
    elif lat is None or lng is None:
        flash("Latitude and longitude are required.", "error")
    else:
        stations_col.update_one(
            {"_id": station_object_id},
            {
                "$set": {
                    "name": name,
                    "location": location,
                    "type": station_type,
                    "availability": availability,
                    "coordinates": {"lat": lat, "lng": lng},
                }
            },
        )
        flash("Station updated successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/station/<station_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_station(station_id):
    station_object_id = oid(station_id)
    if not station_object_id:
        flash("Invalid station id.", "error")
    else:
        stations_col.delete_one({"_id": station_object_id})
        flash("Station deleted successfully.", "success")
    return redirect(url_for("admin_dashboard"))


seed_dummy_data()


if __name__ == "__main__":
    app.run(debug=True)
