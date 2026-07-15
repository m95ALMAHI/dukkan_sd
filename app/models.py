# app/models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Tenant(db.Model):
    """جدول المتاجر (المستأجرين)"""
    __tablename__ = 'tenants'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False) # اسم المتجر بالإنجليزية للرابط
    business_name = db.Column(db.String(100), nullable=False)    # اسم العمل التجاري للظهور
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # علاقة عكسية لجلب مستخدمي ومنتجات هذا المتجر حصراً
    users = db.relationship('User', backref='tenant', lazy=True)
    products = db.relationship('Product', backref='tenant', lazy=True)
    orders = db.relationship('Order', backref='tenant', lazy=True)

class User(db.Model):
    """جدول المستخدمين (يدعم الفصل بين مدير المتجر والزبون)"""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='customer') # 'admin' لمدير المتجر، 'customer' للزبون
    
    __table_args__ = (db.UniqueConstraint('tenant_id', 'email', name='_tenant_email_uc'),)

class Product(db.Model):
    """جدول المنتجات الخاص بكل متجر"""
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(500)) # سنربطها بـ Supabase Storage لاحقاً

class Order(db.Model):
    """جدول الطلبات والفواتير"""
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, completed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
