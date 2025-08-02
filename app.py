from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import json
import os
import random
import time
import threading
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'supersecretkey123!@#'
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# فایل‌های دیتابیس
USERS_FILE = 'users.json'
QUESTIONS_FILE = 'questions.json'

# مدیریت اتاق‌های بازی
class GameManager:
    def __init__(self):
        self.waiting_players = []
        self.rooms = {}
        self.room_counter = 0
        self.lock = threading.Lock()

    def find_match(self, current_player):
        with self.lock:
            # 1. ابتدا بررسی می‌کنیم که آیا بازیکن در حال حاضر در یک اتاق فعال است یا خیر
            for room_id, room in list(self.rooms.items()):
                if current_player in room['players']:
                    if room['status'] == 'finished':
                        del self.rooms[room_id]
                    else:
                        return {'status': 'found_match', 'room_id': room_id}

            # 2. جفت‌سازی هوشمند
            if current_player not in self.waiting_players:
                self.waiting_players.append(current_player)

            if len(self.waiting_players) >= 2:
                player1 = self.waiting_players.pop(0)
                player2 = self.waiting_players.pop(0)
                room_id = self.create_room(player1, player2)
                return {'status': 'found_match', 'room_id': room_id}

            return {'status': 'waiting'}

    def add_to_queue(self, player):
        with self.lock:
            if player not in self.waiting_players:
                self.waiting_players.append(player)
    
    def remove_from_queue(self, player):
        with self.lock:
            if player in self.waiting_players:
                self.waiting_players.remove(player)

    def create_room(self, player1, player2):
        room_id = f"room_{self.room_counter}"
        self.room_counter += 1
        
        self.rooms[room_id] = {
            'players': [player1, player2],
            'scores': {player1: 0, player2: 0},
            'turn': random.choice([player1, player2]),
            'total_rounds': 6,
            'current_round': 0,
            'questions': {},
            'questions_answered_count': {player1: 0, player2: 0},
            'status': 'waiting_for_topic_selection',
            'current_topic': '',
            'current_level': 0,
            'created_at': time.time(),
            'used_combinations': {
                player1: [],
                player2: []
            },
            'used_10_point_question': {
                player1: False,
                player2: False
            },
            'used_remove_two': {
                player1: 0,
                player2: 0
            },
            'question_start_time': 0,
            'current_question_index': 0
        }
        self.cleanup_old_rooms()
        return room_id

    def cleanup_old_rooms(self):
        current_time = time.time()
        expired_rooms = []
        
        for room_id, room in list(self.rooms.items()):
            if current_time - room.get('created_at', current_time) > 3600:
                expired_rooms.append(room_id)
        
        for room_id in expired_rooms:
            del self.rooms[room_id]

game_manager = GameManager()

# توابع کمکی برای مدیریت فایل‌ها
def init_files():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "admin": {
                    "password": generate_password_hash("admin123"),
                    "scores": {"online_match": 0},
                    "completed_questions": []
                }
            }, f, ensure_ascii=False, indent=4)
    
    if not os.path.exists(QUESTIONS_FILE):
        sample_questions = [
            {
                "qText": "پایتخت ایران کدام است؟",
                "options": ["تهران", "مشهد", "اصفهان", "شیراز"],
                "correct": 0,
                "level": 1,
                "category": "جغرافیا",
                "time": 60
            },
            {
                "qText": "کدام سیاره به خاطر حلقه‌هایش معروف است؟",
                "options": ["مریخ", "زهره", "زحل", "مشتری"],
                "correct": 2,
                "level": 2,
                "category": "نجوم",
                "time": 60
            },
            {
                "qText": "سؤال ۱۰ امتیازی نمونه ۱",
                "options": ["گزینه ۱", "گزینه ۲", "گزینه ۳", "گزینه ۴"],
                "correct": 0,
                "level": 10,
                "category": "سوال 10 امتیازی",
                "time": 120
            }
        ]
        with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sample_questions, f, ensure_ascii=False, indent=4)

def load_users():
    if not os.path.exists(USERS_FILE) or os.stat(USERS_FILE).st_size == 0:
        return {}
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=4)

def load_questions():
    if not os.path.exists(QUESTIONS_FILE) or os.stat(QUESTIONS_FILE).st_size == 0:
        return []
    with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_questions(questions):
    with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(questions, f, ensure_ascii=False, indent=4)

def get_topics():
    questions = load_questions()
    topics = sorted(list(set(q['category'] for q in questions)))
    return topics

def get_levels(topic):
    questions = load_questions()
    levels = sorted(list(set(q['level'] for q in questions if q['category'] == topic)))
    return levels

# سیستم احراز هویت
def login_required(route_func):
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            flash('لطفاً ابتدا وارد حساب کاربری خود شوید', 'error')
            return redirect(url_for('login'))
        return route_func(*args, **kwargs)
    wrapper.__name__ = route_func.__name__
    return wrapper

def admin_required(route_func):
    def wrapper(*args, **kwargs):
        if 'username' not in session or session['username'] != 'admin':
            flash('دسترسی محدود به مدیر سیستم', 'error')
            return redirect(url_for('login'))
        return route_func(*args, **kwargs)
    wrapper.__name__ = route_func.__name__
    return wrapper

# روت‌های اصلی برنامه
@app.route('/')
def home():
    return render_template('start.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        
        if not username or not password:
            flash('نام کاربری و رمز عبور نمی‌توانند خالی باشند', 'error')
            return redirect(url_for('register'))
        
        users = load_users()
        if username in users:
            flash('این نام کاربری قبلاً ثبت شده است', 'error')
        else:
            users[username] = {
                'password': generate_password_hash(password),
                'scores': {"online_match": 0},
                "completed_questions": []
            }
            save_users(users)
            flash('ثبت‌نام با موفقیت انجام شد. اکنون می‌توانید وارد شوید', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        users = load_users()
        
        if username not in users:
            flash('نام کاربری وجود ندارد', 'error')
        elif not check_password_hash(users[username]['password'], password):
            flash('رمز عبور اشتباه است', 'error')
        else:
            session.permanent = True
            session['username'] = username
            flash(f'خوش آمدید {username}!', 'success')
            
            if username == 'admin':
                return redirect(url_for('admin_panel'))
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('با موفقیت خارج شدید', 'success')
    return redirect(url_for('home'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        flash(f'درخواست بازنشانی رمز عبور برای {username} ارسال شد.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/dashboard')
@login_required
def dashboard():
    username = session['username']
    users = load_users()
    user_data = users.get(username, {})
    
    return render_template('dashboard.html', 
                           username=username, 
                           scores=user_data.get('scores', {}),
                           total_score=sum(user_data.get('scores', {}).values()))

@app.route('/start_match')
@login_required
def start_match():
    username = session['username']
    game_manager.add_to_queue(username)
    return redirect(url_for('waiting'))

@app.route('/waiting')
@login_required
def waiting():
    return render_template('waiting.html')

@app.route('/check_match_status')
@login_required
def check_match_status():
    username = session['username']
    result = game_manager.find_match(username)
    
    if result['status'] == 'found_match':
        room_id = result['room_id']
        room = game_manager.rooms.get(room_id)
        if room and room['status'] == 'waiting_for_topic_selection':
            if username == room['turn']:
                result['redirect_url'] = url_for('select_topic_for_match', room_id=room_id)
            else:
                result['redirect_url'] = url_for('waiting_for_selection', room_id=room_id)
        else:
            result['redirect_url'] = url_for('quiz_match', room_id=room_id)
            
    return jsonify(result)

@app.route('/waiting_for_selection/<room_id>')
@login_required
def waiting_for_selection(room_id):
    username = session['username']
    room = game_manager.rooms.get(room_id)

    if not room or username not in room['players']:
        return redirect(url_for('dashboard'))

    return render_template('waiting_for_selection.html', 
                           room_id=room_id, 
                           room=room)

@app.route('/check_round_status/<room_id>')
@login_required
def check_round_status(room_id):
    username = session['username']
    room = game_manager.rooms.get(room_id)

    if not room or username not in room['players']:
        return jsonify({'status': 'redirect_home', 'redirect_url': url_for('dashboard')})

    # Check for inactive player (simple session check)
    other_player = [p for p in room['players'] if p != username][0]
    if other_player not in session:
        room['status'] = 'finished'
        return jsonify({'status': 'match_finished', 'redirect_url': url_for('match_result', room_id=room_id)})

    if room['status'] == 'finished':
        return jsonify({'status': 'match_finished', 'redirect_url': url_for('match_result', room_id=room_id)})

    if room['status'] == 'waiting_for_topic_selection':
        if username == room['turn']:
            return jsonify({'status': 'my_turn_to_select', 'redirect_url': url_for('select_topic_for_match', room_id=room_id)})
        else:
            return jsonify({'status': 'waiting_for_opponent_to_select', 'redirect_url': url_for('waiting_for_selection', room_id=room_id)})

    if room['status'] == 'in_progress':
        if room['questions_answered_count'].get(username, 0) < 3:
            return jsonify({'status': 'go_to_questions', 'redirect_url': url_for('quiz_match', room_id=room_id)})
        else:
            # Check if opponent has also answered all 3 questions
            if room['questions_answered_count'].get(other_player, 0) >= 3:
                # Both players are done, start next round/finish game
                return jsonify({'status': 'round_complete', 'redirect_url': url_for('quiz_match', room_id=room_id)})
            else:
                return jsonify({'status': 'waiting_for_opponent_to_answer'})
    
    return jsonify({'status': 'waiting'})

@app.route('/select_topic_for_match/<room_id>', methods=['GET', 'POST'])
@login_required
def select_topic_for_match(room_id):
    username = session['username']
    
    if room_id not in game_manager.rooms:
        flash('اتاق بازی یافت نشد', 'error')
        return redirect(url_for('dashboard'))
    
    room = game_manager.rooms[room_id]
    
    if username != room['turn']:
        return redirect(url_for('waiting_for_selection', room_id=room_id))
    
    if room['status'] == 'finished':
        return redirect(url_for('match_result', room_id=room_id))
    
    questions_data = load_questions()
    topics = sorted(set(q['category'] for q in questions_data))

    used_combinations = [f"{topic}-{level}" for topic, level in room['used_combinations'].get(username, [])]
    
    if request.method == 'POST':
        topic = request.form.get('topic')
        level_str = request.form.get('level')
        
        if not topic or not level_str:
            flash('لطفاً موضوع و سطح را انتخاب کنید.', 'error')
            return redirect(url_for('select_topic_for_match', room_id=room_id))

        if topic == "سوال 10 امتیازی":
            if room['used_10_point_question'][username]:
                flash('شما قبلاً از سؤال ۱۰ امتیازی استفاده کرده‌اید.', 'error')
                return redirect(url_for('select_topic_for_match', room_id=room_id))
            level = 10
        else:
            try:
                level = int(level_str)
            except ValueError:
                flash('سطح انتخابی نامعتبر است.', 'error')
                return redirect(url_for('select_topic_for_match', room_id=room_id))
        
            if (topic, level) in room['used_combinations'][username]:
                flash('شما قبلاً این ترکیب موضوع و سطح را انتخاب کرده‌اید. لطفاً ترکیب دیگری را انتخاب کنید.', 'error')
                return redirect(url_for('select_topic_for_match', room_id=room_id))
        
        filtered_questions = [q for q in questions_data if q['category'] == topic and q['level'] == level]
        
        if len(filtered_questions) < 3:
            flash(f'تعداد سوالات کافی برای "{topic}" در سطح {level} وجود ندارد', 'error')
            return redirect(url_for('select_topic_for_match', room_id=room_id))
        
        selected_questions = random.sample(filtered_questions, 3)
        
        room['questions'] = {i: q for i, q in enumerate(selected_questions)}
        room['current_round'] += 1
        room['questions_answered_count'] = {p: 0 for p in room['players']}
        room['status'] = 'in_progress'
        room['current_topic'] = topic
        room['current_level'] = level
        room['question_start_time'] = time.time()
        room['current_question_index'] = 0
        
        if topic == "سوال 10 امتیازی":
            room['used_10_point_question'][username] = True
        else:
            room['used_combinations'][username].append((topic, level))

        flash(f'موضوع "{topic}" برای دور {room["current_round"]} انتخاب شد! آماده باشید', 'success')
        return redirect(url_for('quiz_match', room_id=room_id))
    
    return render_template('select_topic.html',
                           room_id=room_id,
                           topics=topics,
                           is_my_turn=True,
                           current_round=room['current_round'],
                           turn_player=room['turn'],
                           used_combinations=used_combinations)

@app.route('/quiz_match/<room_id>', methods=['GET', 'POST'])
@login_required
def quiz_match(room_id):
    username = session['username']
    
    if room_id not in game_manager.rooms:
        flash('اتاق بازی یافت نشد', 'error')
        return redirect(url_for('dashboard'))
    
    room = game_manager.rooms[room_id]
    
    if username not in room['players']:
        flash('شما عضو این اتاق بازی نیست', 'error')
        return redirect(url_for('dashboard'))

    if room['status'] == 'finished':
        return redirect(url_for('match_result', room_id=room_id))

    answered_count = room['questions_answered_count'].get(username, 0)
    
    if request.method == 'POST':
        try:
            selected_answer_index = int(request.form.get('answer'))
            correct_answer_index = room['questions'][str(answered_count)]['correct']
            
            is_correct = (selected_answer_index == correct_answer_index)
            
            if is_correct:
                if room['questions'][str(answered_count)]['level'] == 10:
                    room['scores'][username] += 10
                else:
                    room['scores'][username] += room['questions'][str(answered_count)]['level']

            room['questions_answered_count'][username] += 1
            
            if all(count >= 3 for count in room['questions_answered_count'].values()):
                if room['current_round'] < room['total_rounds']:
                    current_index = room['players'].index(room['turn'])
                    next_index = (current_index + 1) % 2
                    room['turn'] = room['players'][next_index]
                    room['status'] = 'waiting_for_topic_selection'
                    return redirect(url_for('quiz_match', room_id=room_id))
                else:
                    room['status'] = 'finished'
                    return redirect(url_for('match_result', room_id=room_id))
            
            return redirect(url_for('quiz_match', room_id=room_id))
        
        except (ValueError, TypeError, KeyError) as e:
            flash(f'پاسخ نامعتبر یا خطای داخلی: {e}', 'error')
            return redirect(url_for('quiz_match', room_id=room_id))

    if room['status'] == 'in_progress' and answered_count < 3:
        question_data = room['questions'].get(str(answered_count))
        if not question_data:
            flash('مشکلی در دریافت سوال پیش آمده است', 'error')
            return redirect(url_for('dashboard'))

        # Set question start time if it's the first question of the round
        if answered_count == 0:
            room['question_start_time'] = time.time()
        
        return render_template('quiz_match.html',
                               room_id=room_id,
                               room=room,
                               username=username,
                               question=question_data,
                               question_number=answered_count + 1,
                               answered_all=False)
    else:
        return render_template('quiz_match.html',
                               room_id=room_id,
                               room=room,
                               username=username,
                               answered_all=True)

@app.route('/match_result/<room_id>')
@login_required
def match_result(room_id):
    username = session['username']
    
    if room_id not in game_manager.rooms:
        flash('اتاق بازی یافت نشد', 'error')
        return redirect(url_for('dashboard'))
    
    room = game_manager.rooms[room_id]
    
    if username not in room['players']:
        flash('شما عضو این اتاق بازی نیستید', 'error')
        return redirect(url_for('dashboard'))
    
    player1, player2 = room['players']
    score1 = room['scores'].get(player1, 0)
    score2 = room['scores'].get(player2, 0)
    
    winner = 'مساوی'
    if score1 > score2:
        winner = player1
    elif score2 > score1:
        winner = player2
    
    users = load_users()
    for player in room['players']:
        if player in users:
            users[player]['scores']['online_match'] = users[player]['scores'].get('online_match', 0) + room['scores'][player]
    save_users(users)
    
    return render_template('match_result.html',
                           scores=room['scores'],
                           winner=winner,
                           players=room['players'],
                           rounds_played=room['current_round'],
                           total_rounds=room['total_rounds'])

# بخش مدیریتی
@app.route('/admin')
@admin_required
def admin_panel():
    users = load_users()
    questions = load_questions()
    return render_template('admin_panel.html', 
                           users=users, 
                           question_count=len(questions))

@app.route('/admin/add_question', methods=['GET', 'POST'])
@admin_required
def add_question():
    questions = load_questions()
    topics = sorted(set(q['category'] for q in questions))
    
    if request.method == 'POST':
        try:
            topic = request.form['topic']
            qText = request.form['qText']
            correct = int(request.form['correct'])
            time_limit = int(request.form['time'])
            options = [request.form[f'option{i}'] for i in range(4)]
            
            new_question = {
                'qText': qText,
                'options': options,
                'correct': correct,
                'category': topic,
                'time': time_limit
            }

            if topic == "سوال 10 امتیازی":
                new_question['level'] = 10
            else:
                level = int(request.form['level'])
                new_question['level'] = level
            
            questions.append(new_question)
            save_questions(questions)
            flash('سؤال جدید با موفقیت اضافه شد', 'success')
            return redirect(url_for('admin_panel'))
        
        except ValueError:
            flash('مقادیر عددی نامعتبر', 'error')
    
    return render_template('add_question.html', topics=topics)

@app.route('/admin/questions')
@admin_required
def view_questions():
    questions = load_questions()
    return render_template('list_questions.html', questions=questions)

@app.route('/admin/edit_question/<int:index>', methods=['GET', 'POST'])
@admin_required
def edit_question(index):
    questions = load_questions()
    
    if index < 0 or index >= len(questions):
        flash('سؤال مورد نظر یافت نشد', 'error')
        return redirect(url_for('view_questions'))
    
    question = questions[index]
    topics = sorted(set(q['category'] for q in questions))
    
    if request.method == 'POST':
        try:
            question['qText'] = request.form['qText']
            question['options'] = [request.form[f'option{i}'] for i in range(4)]
            question['correct'] = int(request.form['correct'])
            question['category'] = request.form['topic']
            question['time'] = int(request.form['time'])
            
            if question['category'] == "سوال 10 امتیازی":
                question['level'] = 10
            else:
                question['level'] = int(request.form['level'])

            questions[index] = question
            save_questions(questions)
            flash('سؤال با موفقیت ویرایش شد', 'success')
            return redirect(url_for('view_questions'))
        
        except ValueError:
            flash('مقادیر عددی نامعتبر', 'error')
    
    return render_template('edit_question.html', 
                           question=question, 
                           index=index,
                           topics=topics)

@app.route('/admin/delete_question/<int:index>', methods=['POST'])
@admin_required
def delete_question(index):
    questions = load_questions()
    
    if index < 0 or index >= len(questions):
        flash('سؤال مورد نظر یافت نشد', 'error')
    else:
        del questions[index]
        save_questions(questions)
        flash('سؤال با موفقیت حذف شد', 'success')
    
    return redirect(url_for('view_questions'))

@app.route('/admin/reset_password', methods=['POST'])
@admin_required
def reset_password():
    username = request.form.get('username')
    users = load_users()
    
    if username not in users:
        flash('کاربر مورد نظر یافت نشد', 'error')
    else:
        users[username]['password'] = generate_password_hash('123456')
        save_users(users)
        flash(f'رمز عبور {username} با موفقیت به 123456 تغییر یافت', 'success')
    
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    init_files()
    app.run(host='0.0.0.0', port=8080, debug=True, threaded=False)