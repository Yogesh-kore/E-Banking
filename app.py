import os
import base64
import hashlib
import datetime
import random
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pymongo import MongoClient
from PIL import Image, ImageOps
import io
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')

client = MongoClient('mongodb://localhost:27017/')
db = client['ebanking']
users = db['users']
transactions = db['transactions']

def create_shares(secret_image):
    # Simple deterministic (2,2) visual cryptography
    # Convert to grayscale and binary
    secret = secret_image.convert('1')  # Binary image
    width, height = secret.size
    share1 = Image.new('1', (width * 2, height))
    share2 = Image.new('1', (width * 2, height))
    for y in range(height):
        for x in range(width):
            pixel = secret.getpixel((x, y))
            # Deterministic patterns
            if pixel == 255:  # White
                pattern = (255, 0) if (x + y) % 2 == 0 else (0, 255)
                share1.putpixel((x*2, y), pattern[0])
                share1.putpixel((x*2+1, y), pattern[1])
                share2.putpixel((x*2, y), pattern[0])
                share2.putpixel((x*2+1, y), pattern[1])
            else:  # Black
                pattern = (255, 0) if (x + y) % 2 == 0 else (0, 255)
                share1.putpixel((x*2, y), pattern[0])
                share1.putpixel((x*2+1, y), pattern[1])
                share2.putpixel((x*2, y), pattern[1])  # Opposite
                share2.putpixel((x*2+1, y), pattern[0])
    return share1, share2

def image_to_base64(image):
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        image_file = request.files['image']
        user = users.find_one({'email': email})
        if user:
            image_data = image_file.read()
            image = Image.open(io.BytesIO(image_data))
            share1, _ = create_shares(image)
            generated = image_to_base64(share1)
            if generated == user['encrypted_text']:
                session['user'] = user['email']
                return redirect(url_for('home'))
            else:
                flash('Invalid image or email')
        else:
            flash('User not found. Please register.')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = {
            'first_name': request.form['first_name'],
            'middle_name': request.form['middle_name'],
            'last_name': request.form['last_name'],
            'gender': request.form['gender'],
            'dob': request.form['dob'],  # <-- Add this line
            'email': request.form['email'],
            'mobile': request.form['mobile'],
            'bank_type': request.form['bank_type'],
            'balance': float(request.form['balance']),
            'transactions': []
        }
        image_file = request.files['image']
        image_data = image_file.read()
        image = Image.open(io.BytesIO(image_data))
        share1, share2 = create_shares(image)
        encrypted_text = image_to_base64(share1)
        data['encrypted_text'] = encrypted_text
        users.insert_one(data)
        return jsonify({'encrypted_text': encrypted_text})
    return render_template('register.html')

@app.route('/home')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = users.find_one({'email': session['user']})
    return render_template('home.html', user=user)

@app.route('/accounts')
def accounts():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = users.find_one({'email': session['user']})
    return render_template('accounts.html', user=user)

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/fund_transfer', methods=['GET', 'POST'])
def fund_transfer():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = users.find_one({'email': session['user']})
    if request.method == 'POST':
        recipient_email = request.form['recipient_email']
        amount = float(request.form['amount'])
        recipient = users.find_one({'email': recipient_email})
        if recipient and amount <= user['balance']:
            users.update_one({'email': session['user']}, {'$inc': {'balance': -amount}})
            users.update_one({'email': recipient_email}, {'$inc': {'balance': amount}})
            transaction = {
                'sender': session['user'],
                'recipient': recipient_email,
                'amount': amount,
                'time': datetime.datetime.now()
            }
            transactions.insert_one(transaction)
            flash('Transfer successful')
        else:
            flash('Invalid transfer')
        return redirect(url_for('fund_transfer'))
    return render_template('fund_transfer.html', user=user)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/transaction_history')
def transaction_history():
    if 'user' not in session:
        return redirect(url_for('login'))
    user_transactions = transactions.find({'$or': [{'sender': session['user']}, {'recipient': session['user']}]})
    return render_template('transaction_history.html', transactions=list(user_transactions))

@app.route('/emi_calculator')
def emi_calculator():
    return render_template('emi_calculator.html')

if __name__ == '__main__':
    app.run(debug=True)