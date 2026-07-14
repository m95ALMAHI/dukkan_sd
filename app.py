import os
import ssl
from datetime import datetime
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

app = Flask(__name__)

# ==========================================
# 1. إعدادات الاتصال وقاعدة البيانات (Supabase SSL)
# ==========================================
raw_db_url = os.environ.get('DATABASE_URL')

if raw_db_url:
    if raw_db_url.startswith("postgres://"):
        database_url = raw_db_url.replace("postgres://", "postgresql+pg8000://", 1)
    elif raw_db_url.startswith("postgresql://"):
        database_url = raw_db_url.replace("postgresql://", "postgresql+pg8000://", 1)
    else:
        database_url = raw_db_url
else:
    database_url = 'sqlite:///fallback.db'

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# إعداد التشفير لحماية الاتصال السحابي
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {
        "ssl_context": ssl_context
    }
}

db = SQLAlchemy(app)


# ==========================================
# 2. الهيكل الهندسي للجداول (SaaS Core Models)
# ==========================================

class Tenant(db.Model):
    """
    جدول المتاجر (Tenants)
    يمثل كل تاجر مشترك في المنصة ببيانات متجره الفريدة.
    """
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # النطاق الفرعي الفريد للمتجر (مثال: my-store.dukkansd.com)
    subdomain = db.Column(db.String(50), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())
    
    # علاقات الربط لسهولة الاستعلام البرمجي
    users = db.relationship('User', backref='tenant', lazy=True, cascade="all, delete-orphan")
    products = db.relationship('Product', backref='tenant', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "subdomain": self.subdomain,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class User(db.Model):
    """
    جدول المستخدمين (Users)
    يمثل مديري الحسابات للمتاجر والمستخدمين التابعين لهم.
    """
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)  # لتخزين كلمات المرور المشفرة مستقبلاً
    role = db.Column(db.String(20), default="admin", nullable=False)  # admin, manager, staff
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active
        }


class Product(db.Model):
    """
    جدول المنتجات (Products)
    معزول بالكامل برمجياً عبر ربطه بالـ tenant_id لضمان خصوصية بيانات التجار.
    """
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)  # استخدام Numeric بدلاً من Float لدقة الحسابات المالية
    stock = db.Column(db.Integer, default=0, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    is_available = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "price": float(self.price),
            "stock": self.stock,
            "image_url": self.image_url,
            "is_available": self.is_available
        }


# ==========================================
# 3. مسارات التحكم والفحص (Endpoints)
# ==========================================

@app.route('/')
def index():
    return jsonify({
        "status": "success",
        "message": "DukkanSD Multi-tenant Engine is core-ready and active.",
        "system_epoch": "2026"
    })

@app.route('/db-test')
def db_test():
    try:
        # إنشاء الجداول الاحترافية الجديدة تلقائياً في Supabase عند أول طلب للمسار
        db.create_all()
        return jsonify({
            "database_status": "Connected & Synchronized Successfully!",
            "architecture": "Multi-tenant Shared-Schema Engine Core",
            "synchronized_tables": ["tenants", "users", "products"]
        })
    except Exception as e:
        return jsonify({
            "database_status": "Failed to sync structures",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
