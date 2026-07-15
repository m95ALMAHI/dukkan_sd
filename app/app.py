import os
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# جلب رابط قاعدة البيانات من متغيرات البيئة (Supabase)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# تعريف جدول تجريبي للتأكد من نجاح الاتصال بـ Supabase
class HealthCheck(db.Model):
    __tablename__ = 'health_check'
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), default="Healthy")

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

if __name__ == '__main__':
    app.run(debug=True)
