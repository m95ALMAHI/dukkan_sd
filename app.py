import os
import ssl
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# 1. جلب رابط قاعدة البيانات الأصلي من متغيرات بيئة Render
raw_db_url = os.environ.get('DATABASE_URL')

# 2. تعديل الرابط برمجياً ليتوافق مع pg8000 وبايثون 3.14
if raw_db_url:
    if raw_db_url.startswith("postgres://"):
        database_url = raw_db_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif raw_db_url.startswith("postgresql://"):
        database_url = raw_db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    else:
        database_url = raw_db_url
else:
    # حل احتياطي لتجنب انهيار السيرفر محلياً إذا لم يتوفر المتغير البيئي
    database_url = 'sqlite:///fallback.db'

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. إعداد الـ SSL ليتوافق مع محرك pg8000 بشكل صحيح لتجاوز حظر الاتصال بـ Supabase
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {
        "ssl_context": ssl_context
    }
}

db = SQLAlchemy(app)

# 4. تعريف جدول تجريبي للتأكد من نجاح الاتصال بـ Supabase
class HealthCheck(db.Model):
    __tablename__ = 'health_check'
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(50), default="Healthy")

# 5. المسارات الأساسية (Routes) لعمل المنصة
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
        # محاولة إنشاء الجدول للتأكد من صحة الاتصال الفعلي بـ Supabase
        db.create_all()
        return jsonify({
            "database_status": "Connected & Synchronized Successfully!",
            "driver_used": "pg8000 with SSL enabled"
        })
    except Exception as e:
        return jsonify({
            "database_status": "Failed to connect",
            "error": str(e)
        }), 500

# 6. محرك التشغيل للتجربة المحلية
if __name__ == '__main__':
    app.run(debug=True)
