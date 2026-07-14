import os
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# جلب الرابط الأصلي من متغيرات البيئة
raw_db_url = os.environ.get('DATABASE_URL')

# تعديل الرابط برمجياً إذا كان يبدأ بـ postgres:// ليصبح postgresql://
if raw_db_url and raw_db_url.startswith("postgres://"):
    database_url = raw_db_url.replace("postgres://", "postgresql://", 1)
else:
    database_url = raw_db_url

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

