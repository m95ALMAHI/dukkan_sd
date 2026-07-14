import os
import ssl
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, jsonify, request, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ==========================================
# 1. الإعدادات ومفتاح التشفير السري
# ==========================================
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'SuperSecretDukkanSDKey2026')

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
# 2. هيكل البيانات المطور (Multi-Tenant SaaS Schema)
# ==========================================

class Tenant(db.Model):
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    subdomain = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    # حقول الـ SaaS والاشتراكات
    whatsapp_number = db.Column(db.String(30), nullable=True, default="249900000000")
    plan = db.Column(db.String(20), default="trial", nullable=False)  # trial, basic, premium
    subscription_status = db.Column(db.String(20), default="active", nullable=False)  # active, suspended, pending
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())
    
    users = db.relationship('User', backref='tenant', lazy=True, cascade="all, delete-orphan")
    products = db.relationship('Product', backref='tenant', lazy=True, cascade="all, delete-orphan")
    receipts = db.relationship('SubscriptionReceipt', backref='tenant', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "subdomain": self.subdomain,
            "whatsapp_number": self.whatsapp_number,
            "plan": self.plan,
            "subscription_status": self.subscription_status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True) # قد يكون فارغاً للـ Super Admin
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="admin", nullable=False)  # super_admin, admin, staff
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
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
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


class SubscriptionReceipt(db.Model):
    __tablename__ = 'subscription_receipts'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False)
    transaction_ref = db.Column(db.String(100), nullable=False)  # رقم الإيصال أو الرقم المرجعي
    receipt_image = db.Column(db.String(500), nullable=True)  # رابط صورة الإيصال المرفوع
    status = db.Column(db.String(20), default="pending", nullable=False)  # pending, approved, rejected
    submitted_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)


# ==========================================
# 3. مزخرف الحماية والتأكد من التوكن (JWT Decorator)
# ==========================================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"status": "error", "message": "Access token is missing!"}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.filter_by(id=data['user_id']).first()
            if not current_user or not current_user.is_active:
                raise Exception("User not found or suspended")
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token has expired!"}), 401
        except Exception as e:
            return jsonify({"status": "error", "message": "Token is invalid!", "detail": str(e)}), 401

        return f(current_user, *args, **kwargs)
    return decorated


# ==========================================
# 4. منافذ التحكم والـ APIs العامة
# ==========================================

@app.route('/')
def index():
    return jsonify({
        "status": "success",
        "message": "Welcome to DukkanSD Multi-tenant SaaS Platform.",
        "version": "2.0.0"
    })


# ------------------------------------------
# أ) منفذ تحديث قواعد البيانات سحابياً (Safe DB Migration Endpoint)
# ------------------------------------------
@app.route('/api/v1/migrate-db')
def migrate_database():
    try:
        # ينشئ الجداول الجديدة بالكامل دون تدمير البيانات القديمة
        db.create_all()
        return jsonify({"status": "success", "message": "Database schema migrated and updated successfully."})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500


# ------------------------------------------
# ب) منفذ تسجيل تاجر جديد (مفتوح للعامة)
# ------------------------------------------
@app.route('/api/v1/register', methods=['POST'])
def register_tenant():
    data = request.get_json() or {}
    required_fields = ['shop_name', 'subdomain', 'admin_username', 'admin_email', 'admin_password']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({"status": "error", "message": f"Missing required fields: {missing_fields}"}), 400

    if Tenant.query.filter_by(subdomain=data['subdomain'].lower()).first():
        return jsonify({"status": "error", "message": "Subdomain is already registered"}), 400
    if User.query.filter_by(email=data['admin_email'].lower()).first():
        return jsonify({"status": "error", "message": "Email is already registered"}), 400

    try:
        # حجز المتجر الجديد مع باقة تجريبية لمدة 14 يوماً تلقائياً
        trial_end = datetime.now(timezone.utc) + timedelta(days=14)
        new_tenant = Tenant(
            name=data['shop_name'],
            subdomain=data['subdomain'].lower(),
            plan="trial",
            subscription_status="active",
            expires_at=trial_end
        )
        db.session.add(new_tenant)
        db.session.flush()

        hashed_password = generate_password_hash(data['admin_password'])
        new_admin = User(
            tenant_id=new_tenant.id,
            username=data['admin_username'],
            email=data['admin_email'].lower(),
            password_hash=hashed_password,
            role="admin"
        )
        db.session.add(new_admin)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Tenant and administrator account created successfully.",
            "tenant": new_tenant.to_dict(),
            "admin": new_admin.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Transaction failed", "detail": str(e)}), 500


# ------------------------------------------
# ج) منفذ تسجيل الدخول
# ------------------------------------------
@app.route('/api/v1/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    if 'email' not in data or 'password' not in data:
        return jsonify({"status": "error", "message": "Email and password are required"}), 400

    user = User.query.filter_by(email=data['email'].lower()).first()
    
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({"status": "error", "message": "Invalid email or password"}), 401

    if user.role != "super_admin":
        if not user.is_active or user.tenant.subscription_status != "active":
            return jsonify({"status": "error", "message": "Your account or shop is suspended. Please contact admin."}), 403

    token_payload = {
        "user_id": user.id,
        "tenant_id": user.tenant_id if user.tenant else None,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }
    
    token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({
        "status": "success",
        "message": "Authentication successful",
        "token": token,
        "role": user.role,
        "shop_name": user.tenant.name if user.tenant else "Super Platform Admin"
    })


# ------------------------------------------
# د) مسار استعراض متجر العميل ديناميكياً (مع ميزة فحص الاشتراك)
# ------------------------------------------
@app.route('/store/<subdomain>')
def view_store(subdomain):
    tenant = Tenant.query.filter_by(subdomain=subdomain.lower()).first()
    if not tenant:
        return jsonify({"status": "error", "message": "Store not found"}), 404
    
    # حماية SaaS الصارمة: إذا تم إيقاف الاشتراك، لا يظهر المتجر وتظهر رسالة معلقة احترافية!
    if tenant.subscription_status != "active":
        return render_template('suspended.html', tenant_name=tenant.name)
        
    products = Product.query.filter_by(tenant_id=tenant.id, is_available=True).all()
    return render_template('store.html', tenant=tenant, products=products)


# ------------------------------------------
# هـ) إدارة المنتجات عبر الـ API (مع دعم العزل)
# ------------------------------------------
@app.route('/api/v1/products', methods=['GET', 'POST'])
def handle_products_api():
    # كطريقة سريعة، جلب معرف المتجر من الهيدر للاختبار، أو استخرجه من الجلسة
    tenant_id = request.headers.get('X-Tenant-ID', 1)
    tenant = Tenant.query.get(int(tenant_id))
    if not tenant or tenant.subscription_status != "active":
        return jsonify({"status": "error", "message": "Tenant is inactive or suspended"}), 403

    if request.method == 'POST':
        data = request.get_json() or {}
        try:
            new_product = Product(
                tenant_id=tenant.id,
                name=data['name'],
                description=data.get('description'),
                price=data['price'],
                stock=data.get('stock', 0),
                image_url=data.get('image_url')
            )
            db.session.add(new_product)
            db.session.commit()
            return jsonify({"status": "success", "product": new_product.to_dict()}), 201
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500

    products = Product.query.filter_by(tenant_id=tenant.id).all()
    return jsonify({
        "status": "success",
        "tenant_name": tenant.name,
        "products": [p.to_dict() for p in products]
    })


# ------------------------------------------
# و) مسار لوحة التحكم للتاجر (Merchant Dashboard)
# ------------------------------------------
@app.route('/admin/dashboard')
def admin_dashboard():
    tenant = Tenant.query.first() # كحساب افتراضي للمتجر الأول المسجل للتجريب السريع
    if not tenant:
        return jsonify({"status": "error", "message": "No merchants registered yet"}), 404
        
    products = Product.query.filter_by(tenant_id=tenant.id).all()
    return render_template('dashboard.html', 
                           tenant_name=tenant.name, 
                           subdomain=tenant.subdomain, 
                           products=products)


if __name__ == '__main__':
    app.run(debug=True)
