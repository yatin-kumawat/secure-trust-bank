from flask import Flask, render_template, request, redirect, session, flash
from flask_session import Session
import random, smtplib, mysql.connector
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import send_file

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import os

from email.mime.text import MIMEText

from dotenv import load_dotenv

import threading
import time

from apscheduler.schedulers.background import BackgroundScheduler
#apscheduler to run interest calculation daily (it checks database for savings accounts and adds interest once every year)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
app.permanent_session_lifetime = timedelta(minutes = 5)  # Auto-expire session
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Email OTP configuration
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")


def db_conn():
    return mysql.connector.connect(host="localhost",
                                user="root",
                                password="yatin123",
                                database="bank_info")


# Home
@app.route('/')
def index():
    return render_template('index.html')


# New customer form
@app.route('/new_customer')
def new_customer():
    return render_template('new_customer.html')


@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'GET':
        if 'new_user' in session:
            otp_sent = session.get('otp_sent_time')
            if otp_sent:
                sent_time = datetime.strptime(otp_sent, '%Y-%m-%d %H:%M:%S')
                now = datetime.now()
                remaining = max(0, 120 - int((now - sent_time).total_seconds()))
            else:
                remaining = 0

            return render_template("verify_email.html", countdown=remaining)

        else:
            return redirect('/new_customer')  # fallback if no session data

    if request.method == 'POST':
        data = request.form.to_dict()
        session['new_user'] = data

        try:
            # Check if mobile already registered
            con = db_conn()
            cur = con.cursor()
            cur.execute("SELECT acc_no FROM bank_info WHERE mobile_no = %s", (data['mobile'],))
            if cur.fetchone():
                con.close()
                return render_template(
                    "error.html",
                    title="Mobile Number Already Registered",
                    icon="📞",
                    icon_color="red",
                    title_color="red",
                    message="This mobile number is already registered. Please use a different number.",
                    back_url="/new_customer",
                    back_text="Restart Registration"
                )
            con.close()

            # ✅ OTP logic (after passing validation)
            now = datetime.now()
            otp = str(random.randint(100000, 999999))
            session['email_otp'] = otp
            session['otp_sent_time'] = now.strftime('%Y-%m-%d %H:%M:%S')
            session['otp_resend_count'] = 1
            remaining = 120  # OTP just sent now

            # Send OTP Email
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            msg = f"Subject: Email Verification\n\nYour verification OTP is {otp}. It is valid for 2 minutes."
            server.sendmail(SENDER_EMAIL, data['email'], msg)
            server.quit()

            return render_template("verify_email.html", countdown=remaining)

        except Exception as e:
            return f"Failed to send email: {str(e)}"
        except Exception as e:
            return f"Failed to send email: {str(e)}"
    
@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    data = session.get('new_user')

    if not data:
        return render_template(
            "error.html",
            title="Session Expired",
            icon="⌛",
            icon_color="red",
            title_color="red",
            message="Your session has expired. Please fill the form again.",
            back_url="/new_customer",
            back_text="Restart Registration"
        )

    # OTP resend limiter
    now = datetime.now()
    last_sent = session.get('otp_sent_time')
    resend_count = session.get('otp_resend_count', 0)

    if last_sent:
        elapsed = now - datetime.strptime(last_sent, '%Y-%m-%d %H:%M:%S')
        if elapsed < timedelta(seconds=60):
            resend_count += 1
            if resend_count > 3:
                return render_template(
                    "error.html",
                    title="Too Many Requests",
                    icon="🚫",
                    icon_color="red",
                    title_color="red",
                    message="You can request OTP only 3 times per minute. Please wait and try again.",
                    back_url="/create_account",
                    back_text="Back to OTP Entry"
                )
        else:
            resend_count = 1  # reset count if enough time passed
    else:
        resend_count = 1

    # Generate and send new OTP
    otp = str(random.randint(100000, 999999))
    session['email_otp'] = otp
    
    session['otp_resend_count'] = resend_count
    session['otp_sent_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    #correcting otp time
    # Get the updated sent time from session
    otp_sent = session.get('otp_sent_time')
    if otp_sent:
        sent_time = datetime.strptime(otp_sent, '%Y-%m-%d %H:%M:%S')
        remaining = max(0, 120 - int((now - sent_time).total_seconds()))
    else:
        remaining = 0


    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        msg = f"Subject: Resent Email Verification\n\nYour new verification OTP is {otp}. It is valid for 2 minutes."
        server.sendmail(SENDER_EMAIL, data['email'], msg)
        server.quit()

        flash("New OTP sent successfully.")
        return render_template("verify_email.html", countdown=remaining)

    except Exception as e:
        return f"Failed to resend OTP: {str(e)}"


#to send account creation email after successful registration
def send_account_creation_email(email, name, acc_no, pin):
    subject = "Welcome to Secure Trust Bank - Account Created"
    body = f"""Hello {name},

Your bank account has been successfully created.

Account No: {acc_no}
PIN: {pin}

You can now log in to your account using your Account Number and PIN.

Thank you for choosing Secure Trust Bank.

Regards,
Secure Trust Bank"""

    try:
        msg = MIMEText(body, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = email

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"[Email Error] Failed to send account creation email: {str(e)}")



@app.route('/confirm_account', methods=['POST'])
def confirm_account():
    try:
        con = db_conn()
        cur = con.cursor()

        data = session.get('new_user')
        entered_otp = request.form['otp']
        correct_otp = session.get('email_otp')
        
        #check if otp expired
        otp_time_str = session.get('otp_sent_time')
        if otp_time_str:
            otp_time = datetime.strptime(otp_time_str, '%Y-%m-%d %H:%M:%S')
            if datetime.now() - otp_time > timedelta(minutes=2):
                return render_template(
                    "error.html",
                    title="OTP Expired",
                    icon="⏰",
                    icon_color="orange",
                    title_color="orange",
                    message="The OTP has expired. Please click 'Resend OTP' to get a new one.",
                    back_url="/create_account",
                    back_text="Back to OTP Entry"
        )

        # Check OTP
        if not correct_otp or entered_otp != correct_otp:
            con.close()
            return render_template(
                "error.html",
                title="Invalid OTP",
                icon="❌",
                icon_color="red",
                title_color="red",
                message="The OTP you entered is incorrect. Please try again.",
                back_url="/create_account",
                back_text="Enter OTP Again"
            )
            
        # ✅ Minimum balance enforcement
        acc_type = data['account']
        initial_amt = int(data['amount'])

        required_min = 1000 if acc_type == "Savings" else 10000
        if initial_amt < required_min:
            return render_template(
                "error.html",
                title="Minimum Deposit Required",
                icon="⚠️",
                icon_color="orange",
                title_color="orange",
                message=f"A minimum deposit of ₹{required_min} is required to open a <b>{acc_type}</b> account.<br>You entered ₹{initial_amt}.",
                back_url="/new_customer",
                back_text="Restart Registration")

        # Proceed with account creation
        acc_no = random.randint(4100000000, 4199999999)
        pin = data['pin']
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


        cur.execute(
            """INSERT INTO bank_info (name, city, dob, gender, account, amount, acc_no, mobile_no, date, email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (data['name'], data['city'], data['dob'], data['gender'], data['account'], data['amount'], acc_no, data['mobile'], now, data['email'])
        )

        cur.execute(
            """INSERT INTO all_data (name, city, dob, gender, account, amount, acc_no, mobile_no, date, deleted_account, acc_delete_date, email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NULL, %s)""",
            (data['name'], data['city'], data['dob'], data['gender'], data['account'], data['amount'], acc_no, data['mobile'], now, data['email'])
        )

        cur.execute("INSERT INTO pin_info (acc_no, pin) VALUES (%s, %s)", (acc_no, pin))

        cur.execute(f"""CREATE TABLE IF NOT EXISTS user_{acc_no} (
                        description VARCHAR(100) DEFAULT NULL,
                        transaction_date DATETIME,
                        deposit INT,
                        withdraw INT,
                        balance INT)""")

        cur.execute(
            f"""INSERT INTO user_{acc_no} (description, transaction_date, deposit, withdraw, balance)
                VALUES (%s,%s, %s, %s, %s)""",
            ("Initial Self Deposit", now, int(data['amount']), 0, int(data['amount']))
        )

        con.commit()
        con.close()

        session.pop('new_user', None)
        session.pop('email_otp', None)

        send_account_creation_email(data['email'], data['name'], acc_no, pin)

        return render_template("account_success.html", acc_no=acc_no, pin=pin)

    except Exception as e:
        return f"An error occurred: {str(e)}", 500


# OTP Login for existing user
@app.route('/otp_login')
def otp_login():
    return render_template('existing_user_login.html')


@app.route('/pin_login', methods=['GET', 'POST'])
def pin_login():
    now = datetime.now()

    #Cooldown active?
    cooldown_until = session.get('pin_lock_until')
    if cooldown_until:
        cooldown_dt = datetime.strptime(cooldown_until, "%Y-%m-%d %H:%M:%S")
        if now < cooldown_dt:
            remaining = int((cooldown_dt - now).total_seconds())
            return render_template("pin_login.html",
                                cooldown=True,
                                remaining=remaining)

    if request.method == 'GET':
        session['pin_attempts'] = 0
        session.pop('pin_lock_until', None)
        return render_template("pin_login.html")

    acc_no = request.form['acc_no']
    pin = request.form['pin']

    # Block after 3 failed attempts
    if session.get('pin_attempts', 0) >= 3:
        session['pin_lock_until'] = (
            now + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        return render_template("pin_login.html", cooldown=True, remaining=60)

    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT pin FROM pin_info WHERE acc_no = %s", (acc_no, ))
    result = cur.fetchone()
    cur.close()
    con.close()

    if result and result[0] == pin:
        session['acc_no'] = acc_no
        session.pop('pin_attempts', None)
        session.pop('pin_lock_until', None)
        return redirect('/dashboard')
    else:
        session['pin_attempts'] = session.get('pin_attempts', 0) + 1
        if session['pin_attempts'] >= 3:
            session['pin_lock_until'] = (
                now + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
            return render_template("pin_login.html",
                                cooldown=True,
                                remaining=60)
        return render_template("pin_login.html", shake=True)


@app.route('/send_otp', methods=['POST'])
def send_otp():
    acc_no = request.form.get('acc_no') or session.get('acc_no')
    pin = request.form.get('pin')
    now = datetime.now()

    # ✅ Check missing inputs
    if not acc_no or not pin:
        return render_template(
            "error.html",
            title="Missing Details",
            icon="❌",
            icon_color="red",
            title_color="red",
            message="Account number or PIN missing. Please try again.",
            back_url="/otp_login",
            back_text="Retry Login")

    # ✅ Verify PIN from DB
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT pin FROM pin_info WHERE acc_no = %s", (acc_no,))
    result = cur.fetchone()

    if not result or str(result[0]) != str(pin):
        cur.close()
        con.close()
        return render_template("error.html",
            title="Invalid Credentials",
            icon="🔐",
            icon_color="red",
            title_color="red",
            message="Account number and PIN do not match.",
            back_url="/otp_login",
            back_text="Retry Login")

    # ✅ Fetch registered email from bank_info
    cur.execute("SELECT email FROM bank_info WHERE acc_no = %s", (acc_no,))
    email_result = cur.fetchone()
    cur.close()
    con.close()

    if not email_result or not email_result[0]:
        return render_template("error.html",
            title="Email Not Found",
            icon="📭",
            icon_color="orange",
            title_color="orange",
            message="No registered email found for this account.",
            back_url="/otp_login",
            back_text="Retry Login")

    email = email_result[0]

    # ✅ OTP resend limit logic
    last_sent = session.get('login_otp_sent_time')
    resend_count = session.get('otp_resend_count', 0)

    if last_sent:
        elapsed = now - datetime.strptime(last_sent, '%Y-%m-%d %H:%M:%S')
        if elapsed < timedelta(seconds=60):
            resend_count += 1
            if resend_count > 3:
                return render_template("error.html",
                    title="Too Many Requests",
                    icon="🚫",
                    icon_color="red",
                    title_color="red",
                    message="You can request OTP only 3 times per minute. Please wait and try again.",
                    back_url="/verify_otp",
                    back_text="Go Back")
        else:
            resend_count = 1
    else:
        resend_count = 1
        
    session['otp_resend_count'] = resend_count
    session['otp_sent_time'] = now.strftime('%Y-%m-%d %H:%M:%S')  # ✅ update this here
        
    # ✅ Check if the account is OTP-locked (from pin_info table)
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT otp_lock_until FROM pin_info WHERE acc_no = %s", (acc_no,))
    lock_check = cur.fetchone()

    if lock_check and lock_check[0]:
        lock_until = lock_check[0]
        now = datetime.now()
        if now < lock_until:
            remaining = (lock_until - now).seconds
            cur.close()
            con.close()
            return render_template("error.html",
                title="Account Locked",
                icon="🚫",
                icon_color="red",
                title_color="red",
                message=f"This account is temporarily locked due to repeated incorrect OTP attempts. Try again in {remaining // 60}m {remaining % 60}s.",
                back_url="/",
                back_text="Return Home")

    # ✅ Generate OTP
    otp = str(random.randint(100000, 999999))
    otp_expires = datetime.now() + timedelta(minutes=2)
    
    # ✅ Save to session
    session.permanent = True
    session['acc_no'] = acc_no
    session['pin'] = pin
    
    # ✅ Store OTP + expiry in DB
    cur.execute("UPDATE pin_info SET otp=%s, otp_expires_at=%s WHERE acc_no=%s", (otp, otp_expires, acc_no))
    con.commit()

    try:
        recipient = email.strip()

        msg = MIMEText(f"Your OTP is {otp}. It will expire in 2 minutes.", _charset="utf-8")
        msg["Subject"] = "Your OTP"
        msg["From"] = SENDER_EMAIL
        msg["To"] = recipient  # This shows in email header

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)

        # ✅ Send to recipient as list (not string)
        server.sendmail(SENDER_EMAIL, [recipient], msg.as_string())
        server.quit()

        return redirect('/verify_otp')

    except Exception as e:
        return f"Failed to send OTP: {str(e)}", 500



@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'GET':
        acc_no = session.get('acc_no')
        pin = session.get('pin')
        if not acc_no:
            return render_template(
            "error.html",
            title="Session Expired",
            icon="⏰",
            icon_color="orange",
            title_color="orange",
            message="Your session has expired. Please log in again.",
            back_url="/otp_login",
            back_text="Go to Login"
        )

        con = db_conn()
        cur = con.cursor()
        cur.execute("SELECT otp_expires_at FROM pin_info WHERE acc_no = %s", (acc_no,))
        result = cur.fetchone()
        con.close()
        
        otp_sent = session.get('otp_sent_time')
        if otp_sent:
            sent_time = datetime.strptime(otp_sent, '%Y-%m-%d %H:%M:%S')
            remaining = max(0, 120 - int((datetime.now() - sent_time).total_seconds()))
        else:
            remaining = 0

        return render_template("verify_otp.html", countdown=remaining)
    
    if request.method == 'POST':   
        acc_no = session.get('acc_no')
        pin = session.get('pin')
        entered_otp = request.form['otp']

        con = db_conn()
        cur = con.cursor()

        # Fetch OTP-related info from database
        cur.execute(
            "SELECT otp, otp_expires_at, otp_attempts, otp_lock_until FROM pin_info WHERE acc_no = %s",
            (acc_no,)
        )
        result = cur.fetchone()

        if not result:
            cur.close()
            con.close()
            return render_template("error.html",
                title="Account Not Found",
                icon="❌",
                icon_color="red",
                title_color="red",
                message="Invalid account number.",
                back_url="/otp_login",
                back_text="Retry Login")

        stored_otp, otp_expires_at, attempts, lock_until = result
        now = datetime.now()
        
        # ✅ Check if account is locked
        if lock_until and now < lock_until:
            remaining = (lock_until - now).seconds
            cur.close()
            con.close()
            return render_template("error.html",
                title="Account Locked",
                icon="⛔",
                icon_color="red",
                title_color="red",
                message=f"Too many incorrect OTP entries. Try again in {remaining // 60}m {remaining % 60}s.",
                back_url="/",
                back_text="Return Home")

        # ✅ Check if OTP is expired
        if not otp_expires_at or now > otp_expires_at:
            cur.close()
            con.close()
            return render_template("error.html",
                title="OTP Expired",
                icon="⏰",
                icon_color="orange",
                title_color="orange",
                message="Your OTP has expired. Please request a new one.",
                back_url="/otp_login",
                back_text="Retry Login")

        # ✅ Check if OTP is correct
        if entered_otp == stored_otp:
            # Reset OTP fields and login session
            cur.execute("UPDATE pin_info SET otp_attempts=0, otp_lock_until=NULL, otp=NULL, otp_expires_at=NULL WHERE acc_no=%s", (acc_no,))
            con.commit()
            cur.close()
            con.close()

            session.permanent = True
            session['acc_no'] = acc_no
            session['user_logged_in'] = True
            
            session.pop('otp_sent_time', None)
            session.pop('otp_resend_count', None)

            return redirect('/dashboard')

        # ❌ Incorrect OTP
        attempts += 1

        if attempts >= 3:
            lock_until = now + timedelta(hours=1)
            cur.execute("UPDATE pin_info SET otp_attempts=%s, otp_lock_until=%s WHERE acc_no=%s", (attempts, lock_until, acc_no))
            con.commit()
            cur.close()
            con.close()
            return render_template("error.html",
                title="Account Locked",
                icon="⛔",
                icon_color="red",
                title_color="red",
                message="Too many incorrect OTP entries. Your account has been locked for 1 hour.",
                back_url="/",
                back_text="Return Home")
        else:
            cur.execute("UPDATE pin_info SET otp_attempts=%s WHERE acc_no=%s", (attempts, acc_no))
            con.commit()
            cur.close()
            con.close()
            return render_template("error.html",
                title="Invalid OTP",
                icon="❌",
                icon_color="red",
                title_color="red",
                message=f"Incorrect OTP. {3 - attempts} attempt(s) remaining.",
                back_url="/verify_otp",
                back_text="Retry OTP")

#clear lock accounts (locked for 1 hour because of wrong otp 3 times)
# This function runs every 5 minutes to clear expired OTP locks
def clear_expired_otp():
    while True:
        try:
            con = db_conn()
            cur = con.cursor()

            # ✅ Clear expired OTPs
            cur.execute("""
                UPDATE pin_info
                SET otp = NULL, otp_expires_at = NULL
                WHERE otp_expires_at IS NOT NULL AND otp_expires_at < NOW()
            """)

            # ✅ Clear expired locks
            cur.execute("""
                UPDATE pin_info
                SET otp_attempts = 0, otp_lock_until = NULL
                WHERE otp_lock_until IS NOT NULL AND otp_lock_until < NOW()
            """)

            con.commit()
            cur.close()
            con.close()

            print("[OTP CLEANUP] Expired OTPs and locks cleared.")

        except Exception as e:
            print("[OTP CLEANUP ERROR]", str(e))

        time.sleep(600)  # Run every 5 minutes



# Dashboard
@app.route('/dashboard')
def dashboard():
    
    if not session.get('user_logged_in'):
        flash("You must log in to access the dashboard.")
        return redirect('/otp_login')
    
    acc_no = session.get('acc_no')
    expires_at = datetime.now() + app.permanent_session_lifetime
    if not acc_no:
        return redirect('/otp_login')

    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT name, amount FROM bank_info WHERE acc_no=%s",
                (acc_no, ))
    user = cur.fetchone()
    return render_template('dashboard.html', user=user, acc_no=acc_no, expires_at=expires_at.strftime('%Y-%m-%d %H:%M:%S'))


# Deposit
@app.route('/deposit', methods=['POST'])
def deposit():
    
    if not session.get('user_logged_in'):
        return redirect('/otp_login')
    
    acc_no = session.get('acc_no')
    if not acc_no:
        return redirect('/otp_login')

    amount = int(request.form['amount'])
    amount = int(request.form['amount'])
    if amount <= 0:
        return render_template(
            "error.html",
            title="Invalid Amount",
            icon="🚫",
            icon_color="red",
            title_color="red",
            message="Deposit amount must be greater than zero.",
            back_url="/dashboard",
            back_text="Back to Dashboard")
    con = db_conn()
    cur = con.cursor()
    cur.execute("SELECT amount FROM bank_info WHERE acc_no=%s", (acc_no, ))
    balance = cur.fetchone()[0]
    new_balance = balance + amount
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cur.execute("UPDATE bank_info SET amount=%s WHERE acc_no=%s",
                (new_balance, acc_no))
    cur.execute("UPDATE all_data SET amount=%s WHERE acc_no=%s",
                (new_balance, acc_no))
    cur.execute(
        f"INSERT INTO user_{acc_no} (description, transaction_date, deposit, withdraw, balance) VALUES (%s,%s,%s,%s,%s)",
        ("Self Deposit", now, amount, 0, new_balance))
    con.commit()
    
    # ✅ Get user's email and name
    cur.execute("SELECT name, email FROM bank_info WHERE acc_no=%s", (acc_no,))
    user_info = cur.fetchone()
    name, email = user_info

    # ✅ Send deposit notification
    send_transaction_email(email, acc_no, name, "Deposit", amount, new_balance)
    
    return redirect('/dashboard')


# Withdraw
@app.route('/withdraw', methods=['POST'])
def withdraw():
    
    if not session.get('user_logged_in'):
        return redirect('/otp_login')
    
    acc_no = session.get('acc_no')
    if not acc_no:
        return redirect('/otp_login')
    amount = int(request.form['amount'])
    con = db_conn()
    cur = con.cursor()
    
    # Get current balance and account type
    cur.execute("SELECT amount, account, name, email FROM bank_info WHERE acc_no = %s", (acc_no,))
    result = cur.fetchone()
    if not result:
        con.close()
        return "Account not found", 404

    balance, acc_type, name, email = result

    # Set minimum balance
    min_balance = 1000 if acc_type == "Savings" else 10000

    if balance - amount < min_balance:
        con.close()
        return render_template(
            "error.html",
            title="Minimum Balance Required",
            icon="⚠️",
            icon_color="orange",
            title_color="orange",
            message=f"As a <b>{acc_type}</b> account holder, you must maintain a minimum balance of ₹{min_balance}.<br>Your current balance is ₹{balance}.",
            back_url="/dashboard",
            back_text="Back to Dashboard"
        )

    new_balance = balance - amount
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cur.execute("UPDATE bank_info SET amount=%s WHERE acc_no=%s",
                (new_balance, acc_no))
    cur.execute("UPDATE all_data SET amount=%s WHERE acc_no=%s",
                (new_balance, acc_no))
    cur.execute(
        f"INSERT INTO user_{acc_no} (description, transaction_date, deposit, withdraw, balance) VALUES (%s,%s,%s,%s,%s)",
        ("Self Withdraw", now, 0, amount, new_balance))
    con.commit()
    
    cur.execute("SELECT name, email FROM bank_info WHERE acc_no=%s", (acc_no,))
    user_info = cur.fetchone()
    name, email = user_info

    send_transaction_email(email, acc_no, name, "Withdraw", amount, new_balance)
    
    return redirect('/dashboard')


# Send transaction email after deposit or withdraw
def send_transaction_email(email, acc_no, name, tx_type, amount, balance):
    if "Transfer" in tx_type:
        direction = "to" if "Sent" in tx_type else "from"
        tx_type += f" {direction} {name}"
        
    subject = f"Bank Notification: {tx_type} Successful"
    body = f"""Hello {name},

Your recent transaction of ₹{amount} was successful.

Account No: {acc_no}
Transaction Type: {tx_type}
Amount: ₹{amount}
Available Balance: ₹{balance}
Date & Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Thank you,
Your Bank"""

    try:
        msg = MIMEText(body, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = email

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"[Email Error] Failed to send transaction email: {str(e)}")



# Passbook
@app.route('/passbook')
def passbook():
    
    if not session.get('user_logged_in'):
        return redirect('/otp_login')
    
    acc_no = session.get('acc_no')
    expires_at = datetime.now() + app.permanent_session_lifetime
    if not acc_no:
        return redirect('/otp_login')
    con = db_conn()
    cur = con.cursor()
    cur.execute(f"SELECT * FROM user_{acc_no}")
    data = cur.fetchall()
    return render_template("passbook.html", data=data, expires_at=expires_at.strftime('%Y-%m-%d %H:%M:%S'))


#Passbook filter
# @app.route('/download_passbook_filter', methods=['GET', 'POST'])
# def download_passbook_filter():
#     if not session.get('user_logged_in'):
#         return redirect('/otp_login')

#     if request.method == 'POST':
#         from_date = request.form['from_date']
#         to_date = request.form['to_date']
#         return redirect(f"/download_passbook?from={from_date}&to={to_date}")

#     return render_template("download_filter.html")


# Generate PDF of passbook
@app.route('/download_passbook')
def download_passbook():
    
    if not session.get('user_logged_in'):
        return redirect('/otp_login')
    
    acc_no = session.get('acc_no')
    if not acc_no:
        return redirect('/otp_login')

    con = db_conn()
    cur = con.cursor()

    # Get user details
    cur.execute("SELECT name FROM bank_info WHERE acc_no = %s", (acc_no,))
    user = cur.fetchone()
    name = user[0] if user else "Unknown"

    # Get transaction data
    cur.execute(f"SELECT * FROM user_{acc_no}")
    transactions = cur.fetchall()
    cur.close()
    con.close()

    if not transactions:
        return render_template("error.html",
            title="No Data",
            icon="📭",
            icon_color="gray",
            title_color="gray",
            message="No transactions found to generate passbook.",
            back_url="/dashboard",
            back_text="Back to Dashboard")

    # Extract date range
    start_date = transactions[0][1].strftime('%d-%b-%Y')
    end_date = transactions[-1][1].strftime('%d-%b-%Y')

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()

    # Logo (optional)
    logo_path = os.path.join("static", "logo.png")
    if os.path.exists(logo_path):
        story.append(Image(logo_path, width=100, height=50))

    # Header
    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Bank Passbook</b>", styles['Title']))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Account Holder: <b>{name}</b>", styles['Normal']))
    story.append(Paragraph(f"Account Number: <b>{acc_no}</b>", styles['Normal']))
    story.append(Paragraph(f"Transaction Period: <b>{start_date}</b> to <b>{end_date}</b>", styles['Normal']))
    story.append(Spacer(1, 12))

    # Table header + data
    table_data = [["Description", "Date", "Deposit (Rs)", "Withdraw (Rs)", "Balance (Rs)"]]
    for row in transactions:
        desc, date, dep, wd, bal = row
        table_data.append([
            f"{desc}",
            date.strftime('%d-%b-%Y %H:%M'),
            f"{dep}" if dep else "-",
            f"{wd}" if wd else "-",
            f"{bal}"
        ])

    # Table Styling
    table = Table(table_data, colWidths=[130, 100, 100, 100])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.blue),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))

    story.append(table)
    doc.build(story)

    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"Passbook_{acc_no}.pdf", mimetype='application/pdf')


#Transfer funds
@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    
    if not session.get('user_logged_in'):
        return redirect('/otp_login')
    
    acc_no = session.get('acc_no')
    expires_at = datetime.now() + app.permanent_session_lifetime
    if not acc_no:
        return redirect('/otp_login')

    if request.method == 'GET':
        return render_template("transfer.html", expires_at=expires_at.strftime('%Y-%m-%d %H:%M:%S'))

    try:
        receiver_acc = request.form['receiver']
        amount = int(request.form['amount'])
        
        if amount <= 0:
            return render_template(
            "error.html",
            title="Invalid Amount",
            icon="🚫",
            icon_color="red",
            title_color="red",
            message="Amount must be greater than zero.",
            back_url="/transfer",
            back_text="Try Again"
        )


        con = db_conn()
        cur = con.cursor()

        # Fetch sender info
        cur.execute("SELECT amount, account, name, email FROM bank_info WHERE acc_no = %s", (acc_no,))
        sender = cur.fetchone()
        if not sender:
            return "Sender not found", 404
        sender_balance, acc_type, sender_name, sender_email = sender
        min_balance = 1000 if acc_type == "Savings" else 10000

        if sender_balance - amount < min_balance:
            return render_template(
                "error.html",
                title="Insufficient Balance",
                icon="⚠️",
                icon_color="orange",
                title_color="orange",
                message=f"You must maintain ₹{min_balance} minimum balance. Current: ₹{sender_balance}, trying to transfer ₹{amount}",
                back_url="/dashboard",
                back_text="Back to Dashboard"
            )

        # Fetch receiver info
        cur.execute("SELECT name, amount, email FROM bank_info WHERE acc_no = %s", (receiver_acc,))
        receiver = cur.fetchone()
        if not receiver:
            return render_template(
                "error.html",
                title="Invalid Account",
                icon="❌",
                icon_color="red",
                title_color="red",
                message=f"Receiver account {receiver_acc} not found.",
                back_url="/transfer",
                back_text="Try Again"
            )
        receiver_name, receiver_balance, receiver_email = receiver

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_sender_balance = sender_balance - amount
        new_receiver_balance = receiver_balance + amount

        # Update balances
        cur.execute("UPDATE bank_info SET amount=%s WHERE acc_no=%s", (new_sender_balance, acc_no))
        cur.execute("UPDATE all_data SET amount=%s WHERE acc_no=%s", (new_sender_balance, acc_no))
        cur.execute("UPDATE bank_info SET amount=%s WHERE acc_no=%s", (new_receiver_balance, receiver_acc))
        cur.execute("UPDATE all_data SET amount=%s WHERE acc_no=%s", (new_receiver_balance, receiver_acc))

        # Insert transaction for sender
        cur.execute(f"""INSERT INTO user_{acc_no} (description, transaction_date, deposit, withdraw, balance)
                        VALUES (%s,%s, %s, %s, %s)""", (f"Transferred to {receiver_name}",now, 0, amount, new_sender_balance))

        # Insert transaction for receiver
        cur.execute(f"""INSERT INTO user_{receiver_acc} (description, transaction_date, deposit, withdraw, balance)
                        VALUES (%s,%s, %s, %s, %s)""", (f"Received from {sender_name}", now, amount, 0, new_receiver_balance))

        con.commit()
        con.close()

        # Send emails to both users
        send_transaction_email(sender_email, acc_no, receiver_name, "Transfer Sent", amount, new_sender_balance)
        send_transaction_email(receiver_email, receiver_acc, sender_name, "Transfer Received", amount, new_receiver_balance)

        return render_template("success.html",
            title="Transfer Successful",
            message=f"₹{amount} transferred to A/C {receiver_acc} ({receiver_name}).",
            expires_at=expires_at.strftime('%Y-%m-%d %H:%M:%S'))

    except Exception as e:
        return f"Transfer failed: {str(e)}"

#send email after account deletion
def send_account_deletion_email(email, name, acc_no, amt):
    subject = "Account Deleted - Secure Trust Bank"
    body = f"""Dear {name},

Your bank account (A/C No: {acc_no}) has been successfully deleted from our system.

Final Balance Withdrawal: ₹{amt}
Transaction: Final Withdrawal for Account Closure
Date & Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

If this action was not performed by you, please contact our support team immediately.

Thank you for banking with us.

Regards,
Secure Trust Bank"""

    try:
        msg = MIMEText(body, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = email

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"[Email Error] Failed to send account deletion email: {str(e)}")


# Delete Account
@app.route('/delete_account', methods=['POST'])
def delete_account():
    if not session.get('user_logged_in'):
        return redirect('/otp_login')
    
    acc_no = session.get('acc_no')
    expires_at = datetime.now() + app.permanent_session_lifetime

    if not acc_no:
        return redirect('/otp_login')
    
    con = db_conn()
    cur = con.cursor()
    
    # Get remaining balance
    cur.execute("SELECT amount FROM bank_info WHERE acc_no=%s", (acc_no,))
    result = cur.fetchone()
    amt = result[0] if result else 0
    
    if amt > 0:
        return render_template("error.html",
        title="Cannot Delete Account",
        icon="💰",
        icon_color="orange",
        title_color="orange",
        message=f"Your account still has ₹{amt}. Please withdraw all funds before deleting your account.",
        back_url="/dashboard",
        back_text="Return to Dashboard"
    )


    # Withdraw remaining balance if any
    if amt > 0:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cur.execute("UPDATE bank_info SET amount=0 WHERE acc_no=%s", (acc_no,))
        cur.execute("UPDATE all_data SET amount=0 WHERE acc_no=%s", (acc_no,))
        cur.execute(f"""INSERT INTO user_{acc_no} (description, transaction_date, deposit, withdraw, balance)
                        VALUES (%s, %s, %s, %s, %s)""",
                    ("Final Withdrawal for Account Closure", now, 0, amt, 0))

    # Delete account from bank_info
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("DELETE FROM bank_info WHERE acc_no=%s", (acc_no,))
    cur.execute("UPDATE all_data SET deleted_account=1, acc_delete_date=%s WHERE acc_no=%s", (now, acc_no))

    # Send final email (optional)
    cur.execute("SELECT name, email FROM all_data WHERE acc_no=%s", (acc_no,))
    user = cur.fetchone()
    if user:
        name, email = user
        send_account_deletion_email(email, name, acc_no, amt)

    con.commit()
    cur.close()
    con.close()

    # Clear session
    session.clear()

    return render_template("message.html",
        title="Account Deleted Successfully",
        message="You will be redirected to the homepage shortly.",
        back_url="/",
        back_text="Go to Home",
        expires_at=expires_at.strftime('%Y-%m-%d %H:%M:%S'))


#Session Expired
@app.route('/session_expired')
def session_expired():
    return render_template("session_expired.html")


#Clear session and logout user
@app.route('/user_logout')
def logout():
    session.clear()
    expires_at = datetime.now() + app.permanent_session_lifetime
    return render_template("message.html",
        title="You have been logged out.",
        message="You will be redirected to the login page shortly.",
        back_url="/otp_login",
        back_text="Go to Login",
        expires_at=expires_at.strftime('%Y-%m-%d %H:%M:%S'))


#function to credit interest to savings account annually
def credit_annual_interest():
    con = db_conn()
    cur = con.cursor()

    annual_rate = 0.02
    today = datetime.now().date()

    cur.execute("SELECT acc_no, amount, last_interest_date, email, name FROM bank_info WHERE account = 'Savings'")
    accounts = cur.fetchall()

    for acc_no, balance, last_date, email, name in accounts:
        if last_date is not None and (today - last_date).days < 365:
            continue

        interest = int(balance * annual_rate)
        if interest <= 0:
            continue

        new_balance = balance + interest
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cur.execute("UPDATE bank_info SET amount=%s, last_interest_date=%s WHERE acc_no=%s", (new_balance, today, acc_no))
        cur.execute("UPDATE all_data SET amount=%s WHERE acc_no=%s", (new_balance, acc_no))

        cur.execute(f"""INSERT INTO user_{acc_no} (transaction_date, deposit, withdraw, balance)
                        VALUES (%s, %s, %s, %s)""", (now_str, interest, 0, new_balance))

        send_transaction_email(email, acc_no, name, "Annual Interest", interest, new_balance)

    con.commit()
    cur.close()
    con.close()

    print("✅ Annual interest credited (automated)")


# Manager Access
@app.route('/manager', methods=['GET', 'POST'])
def manager():
    if request.method == 'GET':
        return render_template("manager.html")

    pwd = request.form['password']
    if pwd != "12345":
        return render_template(
            "error.html",
            title="Access Denied",
            icon="🔒",
            icon_color="red",
            title_color="red",
            message="The password you entered is incorrect.",
            back_url="/manager",
            back_text="Back to Manager Login")

    # ✅ Save login session (optional, if you want to protect manager_data)
    session['manager_logged_in'] = True

    return redirect("/manager_data")

#Manager data on login
@app.route('/manager_data', methods=['GET', 'POST'])
def manager_data():
    if not session.get('manager_logged_in'):
        return redirect('/manager')  # 🔒 optional protection

    filter_option = request.form.get('filter', 'all') if request.method == 'POST' else 'all'

    con = db_conn()
    cur = con.cursor()

    if filter_option == 'active':
        cur.execute("SELECT * FROM all_data WHERE deleted_account = 0")
    elif filter_option == 'deleted':
        cur.execute("SELECT * FROM all_data WHERE deleted_account = 1")
    else:
        cur.execute("SELECT * FROM all_data")

    data = cur.fetchall()
    cur.close()
    con.close()

    return render_template("manager_data.html", data=data, selected=filter_option)

#Manager logout
@app.route('/manager_logout')
def manager_logout():
    session.pop('manager_logged_in', None)
    return redirect('/')


def initialize_database():
    # Connect without selecting a database
    con = mysql.connector.connect(host="localhost",
                                user="root",
                                password="yatin123")
    cur = con.cursor()

    # Create the database if it doesn't exist
    cur.execute("CREATE DATABASE IF NOT EXISTS bank_info")
    con.commit()
    cur.close()
    con.close()

    # Now connect to the bank_info database
    con = db_conn()
    cur = con.cursor()

    # Table 1: bank_info
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_info (
            name VARCHAR(50),
            city VARCHAR(30),
            dob date,
            gender VARCHAR(10),
            account VARCHAR(20),
            amount INT DEFAULT 0,
            acc_no BIGINT PRIMARY KEY,
            mobile_no BIGINT,
            date DATETIME,
            email VARCHAR(100),
            last_interest_date DATE DEFAULT NULL
        )
    """)

    # Table 2: all_data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS all_data (
            name VARCHAR(50),
            city VARCHAR(30),
            dob date,
            gender VARCHAR(10),
            account VARCHAR(20),
            amount INT DEFAULT 0,
            acc_no BIGINT PRIMARY KEY,
            mobile_no BIGINT,
            date DATETIME,
            deleted_account INT DEFAULT 0,
            acc_delete_date DATETIME,
            email VARCHAR(100)
        )
    """)

    # Table 3: pin_info
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pin_info (
            acc_no BIGINT PRIMARY KEY,
            pin INT,
            otp_attempts INT DEFAULT 0,
            otp_lock_until DATETIME DEFAULT NULL,
            otp VARCHAR(6),
            otp_expires_at DATETIME DEFAULT NULL
        )
    """)
    #otp_expires_at is used to store when the OTP expires i.e. like 5 minutes
    #otp_lock_until is used to store when the account is locked due to too many incorrect OTP attempts

    con.commit()
    cur.close()
    con.close()


# 🚀 Run the Flask app
if __name__ == '__main__':
    initialize_database()  # 🔧 Initialize DB on startup
    
    scheduler = BackgroundScheduler()
    # Runs once every day at 2:00 AM
    scheduler.add_job(credit_annual_interest, 'cron', hour=2, minute=0)
    scheduler.start()
    
    # Start background OTP cleaner
    threading.Thread(target=clear_expired_otp, daemon=True).start()
    
    app.run(debug=True)
    
# Note: Make sure to replace the email and password with your own credentials.
# Also, ensure that the MySQL server is running and the database is accessible.

#cloudflared tunnel --url http://localhost:8000 or 5000
#command to run in cmd and it will give link to access the app from anywhere
#make sure to run this command in the same directory where app.py is located