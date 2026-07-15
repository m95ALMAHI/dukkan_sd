# app/__init__.py
import os
from flask import Flask, request, abort
from app.models import db, Tenant

def create_app():
    app = Flask(__name__)
    
    # الإعدادات الاحترافية والربط بـ Supabase
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # تحديد الدومين الرئيسي للمنصة للتحكم بالدومينات الفرعية
    # في البيئة المحلية سيكون localhost:5000 وفي سيرفر رندر سيكون dukkansd.com
    app.config['SERVER_NAME'] = os.environ.get('SERVER_NAME', 'localhost:5000')
    
    db.init_app(app)
    
    # معالج ذكي قبل كل طلب (Middleware) لتحديد متجر التاجر الحالي
    @app.before_request
    def get_current_tenant():
        host = request.host.split(':')[0]
        server_name = app.config['SERVER_NAME'].split(':')[0]
        
        if host != server_name:
            # استخراج الدومين الفرعي (اسم المتجر)
            subdomain = host.replace(f".{server_name}", "")
            tenant = Tenant.query.filter_by(name=subdomain, is_active=True).first()
            if not tenant:
                abort(404, description="هذا المتجر غير موجود أو تم إيقافه.")
            # حفظ المتجر الحالي في سياق الطلب ليسهل استدعاؤه في أي مكان بالكود
            request.current_tenant = tenant
        else:
            request.current_tenant = None

    # تسجيل مسارات النظام (Blueprints)
    from app.routes.core import core_bp
    app.register_blueprint(core_bp)
    
    return app
