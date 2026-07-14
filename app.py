import os
import ssl
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ==========================================
# 1. الإعدادات ومفتاح التشفير السري
# ==========================================
# في البيئة الإنتاجية نستخدم متغير بيئي، ومحلياً نستخدم نصاً عشوائياً كاحتياط
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
# 2. هيكل البيانات (Database Models)
# ==========================================

class Tenant(db.Model):
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    subdomain = db.Column(db.String(50), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())
    
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
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="admin", nullable=False)
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


# ==========================================
# 3. مزخرف الحماية والتأكد من التوكن (JWT Decorator)
# ==========================================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # جلب التوكن من الهيدر (Authorization: Bearer <TOKEN>)
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"status": "error", "message": "Access token is missing!"}), 401

        try:
            # فك تشفير التوكن والتحقق من صلاحيته
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.filter_by(id=data['user_id']).first()
            if not current_user or not current_user.is_active:
                raise Exception("User not found or suspended")
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Token has expired!"}), 401
        except Exception as e:
            return jsonify({"status": "error", "message": "Token is invalid!", "detail": str(e)}), 401

        # تمرير بيانات المستخدم والتاجر الحاليين إلى المسار المحمي تلقائياً
        return f(current_user, *args, **kwargs)
    return decorated


# ==========================================
# 4. منافذ التحكم والـ APIs
# ==========================================

@app.route('/')
def index():
    return jsonify({
        "status": "success",
        "message": "Welcome to DukkanSD Multi-tenant JWT Secured API Engine.",
        "version": "1.1.0"
    })


# ------------------------------------------
# أ) منفذ تسجيل تاجر جديد (مفتوح للعامة)
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
        new_tenant = Tenant(
            name=data['shop_name'],
            subdomain=data['subdomain'].lower()
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
# ب) منفذ تسجيل الدخول وتوليد التوكن (Login & Issue Token)
# ------------------------------------------
@app.route('/api/v1/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    if 'email' not in data or 'password' not in data:
        return jsonify({"status": "error", "message": "Email and password are required"}), 400

    user = User.query.filter_by(email=data['email'].lower()).first()
    
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({"status": "error", "message": "Invalid email or password"}), 401

    if not user.is_active or not user.tenant.is_active:
        return jsonify({"status": "error", "message": "Your account or shop is suspended"}), 403

    # توليد توكن ينتهي بعد 24 ساعة
    token_payload = {
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }
    
    token = jwt.encode(token_payload, app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({
        "status": "success",
        "message": "Authentication successful",
        "token": token,
        "shop_name": user.tenant.name,
        "subdomain": user.tenant.subdomain
    })


# ------------------------------------------
# ج) إدارة المنتجات مع العزل التام ومصادقة الـ JWT (Secured Products Route)
# ------------------------------------------
@app.route('/api/v1/products', methods=['GET', 'POST'])
@token_required
def handle_products(current_user):
    # جلب المتجر المربوط مباشرة بالتوكن لضمان الحماية المطلقة وعدم إمكانية التزوير
    tenant = Tenant.query.get(current_user.tenant_id)
    if not tenant or not tenant.is_active:
        return jsonify({"status": "error", "message": "Tenant account associated with token is inactive"}), 403

    # 1. إضافة منتج جديد (محمية ومربوطة تلقائياً بمتجر صاحب التوكن)
    if request.method == 'POST':
        data = request.get_json() or {}
        if 'name' not in data or 'price' not in data:
            return jsonify({"status": "error", "message": "Product 'name' and 'price' are required"}), 400
        
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

    # 2. جلب منتجات هذا المتجر فقط
    products = Product.query.filter_by(tenant_id=tenant.id).all()
    return jsonify({
        "status": "success",
        "tenant_name": tenant.name,
        "product_count": len(products),
        "products": [p.to_dict() for p in products]
    })


if __name__ == '__main__':
    app.run(debug=True)
