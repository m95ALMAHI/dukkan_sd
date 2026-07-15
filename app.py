import os
import ssl
import jwt
import json
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, jsonify, request, render_template, redirect, url_for, session
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

    is_active = db.Column(db.Boolean, default=True, nullable=False)

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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True)
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
    category = db.Column(db.String(55), nullable=False)
    brand = db.Column(db.String(50), nullable=True)
    description = db.Column(db.Text, nullable=True)

    specifications = db.Column(db.JSON, nullable=True, default=dict)

    price = db.Column(db.Numeric(12, 2), nullable=False)
    compare_at_price = db.Column(db.Numeric(12, 2), nullable=True)

    barcode_qr = db.Column(db.String(100), nullable=True, index=True)
    stock = db.Column(db.Integer, default=1, nullable=False)
    image_url = db.Column(db.String(500), nullable=True)
    is_available = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        discount_percentage = 0
        if self.compare_at_price and self.compare_at_price > self.price:
            discount_percentage = int(((self.compare_at_price - self.price) / self.compare_at_price) * 100)

        specs = self.specifications
        if isinstance(specs, str):
            try:
                specs = json.loads(specs)
            except Exception:
                specs = {}

        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "category": self.category,
            "brand": self.brand,
            "description": self.description,
            "specifications": specs or {},
            "price": float(self.price),
            "compare_at_price": float(self.compare_at_price) if self.compare_at_price else None,
            "discount_percentage": discount_percentage,
            "barcode_qr": self.barcode_qr,
            "stock": self.stock,
            "image_url": self.image_url,
            "is_available": self.is_available
        }


class SubscriptionReceipt(db.Model):
    __tablename__ = 'subscription_receipts'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False)
    transaction_ref = db.Column(db.String(100), nullable=False)
    receipt_image = db.Column(db.String(500), nullable=True)
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
# 4. مسارات واجهات العرض (HTML Templates & Sessions)
# ==========================================

@app.route('/')
def index():
    return render_template('landing.html')


@app.route('/register')
def register_page():
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            return render_template('login.html', error="يرجى إدخال البريد الإلكتروني وكلمة المرور.")

        user = User.query.filter_by(email=email.lower().strip()).first()
        if user and check_password_hash(user.password_hash, password):
            if user.role != "super_admin":
                if not user.is_active or user.tenant.subscription_status != "active":
                    return render_template('login.html', error="حسابك أو متجرك معلق حالياً. يرجى التواصل مع الإدارة.")

            session['user_id'] = user.id
            session['tenant_id'] = user.tenant_id
            session['role'] = user.role

            if user.role == 'super_admin':
                return redirect(url_for('super_admin_dashboard_updated'))
            else:
                return redirect(url_for('admin_dashboard'))
        else:
            return render_template('login.html', error="البريد الإلكتروني أو كلمة المرور غير صحيحة.")

    return render_template('login.html')


@app.route('/admin/dashboard')
def admin_dashboard():
    user_id = session.get('user_id')
    tenant_id = session.get('tenant_id')

    if not user_id or not tenant_id:
        return redirect(url_for('login_page'))

    tenant = Tenant.query.get(tenant_id)
    if not tenant or tenant.subscription_status != "active":
        return redirect(url_for('login_page'))

    products = Product.query.filter_by(tenant_id=tenant.id).all()
    return render_template('dashboard.html', tenant=tenant, products=products)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/store/<subdomain>')
def view_store(subdomain):
    tenant = Tenant.query.filter_by(subdomain=subdomain.lower().strip()).first()
    if not tenant:
        return jsonify({"status": "error", "message": "Store not found"}), 404

    if tenant.subscription_status != "active":
        return render_template('suspended.html', tenant_name=tenant.name)

    products = Product.query.filter_by(tenant_id=tenant.id, is_available=True).order_by(Product.created_at.desc()).all()
    return render_template('store.html', tenant=tenant, products=products)


# ==========================================
# 5. منافذ التحكم والـ APIs الخلفية
# ==========================================

@app.route('/api/v1/migrate-db')
def migrate_database():
    try:
        db.create_all()
        return jsonify({"status": "success", "message": "Database schema migrated and updated successfully."})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.route('/api/v1/register', methods=['POST'])
def register_tenant():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    required_fields = ['shop_name', 'subdomain', 'admin_username', 'admin_email', 'admin_password']
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    if missing_fields:
        if request.is_json:
            return jsonify({"status": "error", "message": f"Missing required fields: {missing_fields}"}), 400
        else:
            return render_template('register.html', error="الرجاء ملء جميع الحقول المطلوبة.")

    subdomain = data['subdomain'].strip().lower()
    email = data['admin_email'].strip().lower()
    whatsapp = data.get('whatsapp_number', '249900000000').strip()
    selected_plan = data.get('plan', 'trial')

    if Tenant.query.filter_by(subdomain=subdomain).first():
        msg = "رابط المتجر محجوز مسبقاً، اختر اسماً آخر."
        return jsonify({"status": "error", "message": msg}) if request.is_json else render_template('register.html', error=msg)

    if User.query.filter_by(email=email).first():
        msg = "البريد الإلكتروني مسجل بالفعل."
        return jsonify({"status": "error", "message": msg}) if request.is_json else render_template('register.html', error=msg)

    try:
        days_limit = 14 if selected_plan == "trial" else 30
        expire_date = datetime.now(timezone.utc) + timedelta(days=days_limit)

        new_tenant = Tenant(
            name=data['shop_name'],
            subdomain=subdomain,
            whatsapp_number=whatsapp,
            plan=selected_plan,
            subscription_status="active",
            expires_at=expire_date
        )
        db.session.add(new_tenant)
        db.session.flush()

        hashed_password = generate_password_hash(data['admin_password'])
        new_admin = User(
            tenant_id=new_tenant.id,
            username=data['admin_username'],
            email=email,
            password_hash=hashed_password,
            role="admin"
        )
        db.session.add(new_admin)
        db.session.commit()

        session['user_id'] = new_admin.id
        session['tenant_id'] = new_tenant.id
        session['role'] = new_admin.role

        if request.is_json:
            return jsonify({
                "status": "success",
                "message": "Tenant registered successfully.",
                "tenant": new_tenant.to_dict()
            }), 201
        else:
            return redirect(url_for('admin_dashboard'))

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Transaction failed", "detail": str(e)}), 500


@app.route('/api/v1/login', methods=['POST'])
def login_api():
    data = request.get_json() or {}
    if 'email' not in data or 'password' not in data:
        return jsonify({"status": "error", "message": "Email and password are required"}), 400

    user = User.query.filter_by(email=data['email'].lower().strip()).first()

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


@app.route('/api/v1/products', methods=['GET', 'POST'])
def handle_products_api():
    tenant_id = session.get('tenant_id') or request.headers.get('X-Tenant-ID')
    if not tenant_id:
         return jsonify({"status": "error", "message": "Unauthorized, tenant identification missing"}), 401

    tenant = Tenant.query.get(int(tenant_id))
    if not tenant or tenant.subscription_status != "active":
        return jsonify({"status": "error", "message": "Tenant is inactive or suspended"}), 403

    if request.method == 'POST':
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        product_id = data.get('id')
        specs = {}

        if 'specifications' in data and data['specifications']:
            try:
                if isinstance(data['specifications'], str):
                    specs = json.loads(data['specifications'])
                else:
                    specs = data['specifications']
            except Exception:
                specs = {}
        else:
            for key, value in data.items():
                if key.startswith('spec_') and value.strip():
                    spec_key = key.replace('spec_', '')
                    specs[spec_key] = value

        # التحقق والتحويل الآمن للأسعار والكميات لتجنب انهيار قاعدة البيانات
        try:
            price_val = float(data.get('price', 0))
            compare_price_val = float(data.get('compare_at_price')) if data.get('compare_at_price') else None
            stock_val = int(data.get('stock', 1))
        except (ValueError, TypeError) as val_err:
            return jsonify({"status": "error", "message": f"خطأ في قيم المدخلات الرقمية: {str(val_err)}"}), 400

        try:
            if product_id:
                product = Product.query.filter_by(id=product_id, tenant_id=tenant.id).first_or_404()
                product.name = data.get('name')
                product.brand = data.get('brand')
                product.category = data.get('category')
                product.description = data.get('description')
                product.price = price_val
                product.compare_at_price = compare_price_val
                product.barcode_qr = data.get('barcode_qr') or None
                product.image_url = data.get('image_url') or None
                product.stock = stock_val
                product.specifications = specs
            else:
                product = Product(
                    tenant_id=tenant.id,
                    name=data.get('name'),
                    brand=data.get('brand'),
                    category=data.get('category'),
                    description=data.get('description'),
                    price=price_val,
                    compare_at_price=compare_price_val,
                    barcode_qr=data.get('barcode_qr') or None,
                    image_url=data.get('image_url') or None,
                    stock=stock_val,
                    specifications=specs
                )
                db.session.add(product)

            db.session.commit()
            return jsonify({"status": "success", "message": "تم حفظ المنتج بنجاح!", "product": product.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": f"فشلت العملية: {str(e)}"}), 500

    products = Product.query.filter_by(tenant_id=tenant.id).all()
    return jsonify({
        "status": "success",
        "tenant_name": tenant.name,
        "products": [p.to_dict() for p in products]
    })


@app.route('/super-admin/dashboard')
def super_admin_dashboard_updated():
    if session.get('role') != 'super_admin':
        return redirect(url_for('login_page'))
    tenants = Tenant.query.all()
    receipts = SubscriptionReceipt.query.filter_by(status="pending").all()
    return render_template('super_admin.html', tenants=tenants, receipts=receipts)


@app.route('/api/v1/super-admin/update-tenant', methods=['POST'])
def super_admin_update_tenant():
    if session.get('role') != 'super_admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data = request.get_json() or {}
    tenant_id = data.get('tenant_id')
    new_status = data.get('status')

    if not tenant_id or not new_status:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    tenant = Tenant.query.get(int(tenant_id))
    if not tenant:
        return jsonify({"status": "error", "message": "Tenant not found"}), 404

    try:
        tenant.subscription_status = new_status
        db.session.commit()
        return jsonify({"status": "success", "message": f"Tenant status changed to {new_status}"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/submit-receipt', methods=['POST'])
def submit_receipt():
    data = request.get_json() or {}
    try:
        new_receipt = SubscriptionReceipt(
            tenant_id=int(data['tenant_id']),
            amount_paid=float(data['amount']),
            transaction_ref=data['ref'],
            receipt_image=data.get('image'),
            status="pending"
        )
        db.session.add(new_receipt)
        db.session.commit()
        return jsonify({"status": "success", "message": "Receipt submitted successfully."}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/v1/super-admin/handle-receipt', methods=['POST'])
def super_admin_handle_receipt():
    if session.get('role') != 'super_admin':
        return jsonify({"status": "error", "message": "Unauthorized"}), 403

    data = request.get_json() or {}
    receipt_id = data.get('receipt_id')
    action = data.get('action')

    receipt = SubscriptionReceipt.query.get(int(receipt_id))
    if not receipt:
        return jsonify({"status": "error", "message": "Receipt not found"}), 404

    try:
        receipt.status = action
        receipt.reviewed_at = datetime.now(timezone.utc)

        if action == "approved":
            tenant = Tenant.query.get(receipt.tenant_id)
            tenant.subscription_status = "active"
            if tenant.expires_at:
                # إذا انتهى التاريخ بالفعل، نجدد له من اللحظة الحالية وليس من التاريخ القديم المنتهي
                base_time = max(tenant.expires_at.replace(tzinfo=timezone.utc), datetime.now(timezone.utc))
                tenant.expires_at = base_time + timedelta(days=30)
            else:
                tenant.expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        db.session.commit()
        return jsonify({"status": "success", "message": f"Receipt marked as {action}"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
