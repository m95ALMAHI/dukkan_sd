import os
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# 1. جلب وتصحيح رابط قاعدة البيانات بشكل آمن
raw_db_url = os.environ.get('DATABASE_URL')

if raw_db_url and raw_db_url.startswith("postgres://"):
    database_url = raw_db_url.replace("postgres://", "postgresql://", 1)
else:
    database_url = raw_db_url

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 2. تعريف جدول تجريبي للتأكد من نجاح الاتصال بـ Supabase
class HealthCheck(db.Model):
    __tablename__ = 'health_check'
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), default="Healthy")

# 3. المسارات (Routes) التي تم حذفها بالخطأ
@app.route('/')
def index():
    return jsonify({
        "status": "success",
        "message": "Welcome to DukkanSD API - Professional Multi-tenant SaaS Platform",
        "system": "Online"
    })

@app.route('/db-test')
def db_test():
    try:
        # محاولة إنشاء الجدول للتأكد من صحة الاتصال بـ Supabase
        db.create_all()
        return jsonify({"database_status": "Connected & Synchronized Successfully!"})
    except Exception as e:
        return jsonify({"database_status": "Failed to connect", "error": str(e)}), 500

# 4. محرك تشغيل السيرفر المحلي والتجريبي
if __name__ == '__main__':
    app.run(debug=True)

