import os
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import cloudinary
import cloudinary.uploader
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()
if os.getenv('DATABASE_URL', '').startswith('postgres://'):
    os.environ['DATABASE_URL'] = 'postgresql://' + os.environ['DATABASE_URL'][len('postgres://'):]
if os.getenv('RENDER') and not (os.getenv('DATABASE_URL') and os.getenv('CLOUDINARY_URL') and os.getenv('SECRET_KEY')):
    raise RuntimeError('Production requires DATABASE_URL, CLOUDINARY_URL and SECRET_KEY.')
BASE = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv('SECRET_KEY') or secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///' + str(BASE / 'step_elegant.db')),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=str(BASE / 'static' / 'uploads'),
    MAX_CONTENT_LENGTH=110 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)
if os.getenv('COOKIE_SECURE') == '1' or os.getenv('RENDER'):
    app.config['SESSION_COOKIE_SECURE'] = True
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
app.config['PREFERRED_URL_SCHEME'] = 'https' if os.getenv('RENDER') else 'http'

@app.template_filter('media_url')
def media_url(path):
    if not path:
        return ''
    if path.startswith('https://res.cloudinary.com/'):
        return path
    if path.startswith('uploads/'):
        return url_for('static', filename=path)
    return ''
db = SQLAlchemy(app)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(60), nullable=False, default='Sneakers')
    description = db.Column(db.Text, default='')
    price = db.Column(db.Numeric(10, 2), nullable=False)
    compare_price = db.Column(db.Numeric(10, 2))
    stock = db.Column(db.Integer, default=0, nullable=False)
    sizes = db.Column(db.String(100), default='6,7,8,9,10,11')
    image = db.Column(db.String(500), default='')
    featured = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    media = db.relationship('ProductMedia', backref='product', lazy=True, cascade='all, delete-orphan', order_by='ProductMedia.position')

class ProductMedia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(60), nullable=False)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(30), default='')
    country = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text, default='')
    total = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(30), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    product_name = db.Column(db.String(150), nullable=False)
    size = db.Column(db.String(20), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)

@app.context_processor
def globals_for_templates():
    return {'cart_count': sum(v.get('qty', 0) for v in session.get('cart', {}).values()), 'year': datetime.now().year, 'csrf_token': lambda: session.setdefault('_csrf', secrets.token_urlsafe(32))}

@app.before_request
def csrf_protection():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if not secrets.compare_digest(session.get('_csrf', ''), request.form.get('_csrf', request.headers.get('X-CSRF-Token', ''))):
            abort(400, 'Invalid or missing CSRF token. Refresh the page and try again.')

def admin_only(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('admin_login', next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError()
        return amount.quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        raise ValueError('Enter a valid non-negative price.')

def cart_data():
    items = []
    for key, entry in session.get('cart', {}).items():
        product = db.session.get(Product, entry.get('product_id'))
        if product and product.active and entry.get('size') in [s.strip() for s in product.sizes.split(',')]:
            qty = max(1, min(int(entry.get('qty', 1)), product.stock))
            if qty:
                items.append({'key': key, 'product': product, 'size': entry['size'], 'qty': qty, 'subtotal': product.price * qty})
    return items, sum((i['subtotal'] for i in items), Decimal('0.00'))

@app.get('/')
def home():
    featured = Product.query.filter_by(active=True).order_by(Product.featured.desc(), Product.created_at.desc()).limit(8).all()
    return render_template('home.html', products=featured)

@app.get('/shop')
def shop():
    q = request.args.get('q', '').strip()[:100]
    category = request.args.get('category', '').strip()[:60]
    sort = request.args.get('sort', 'newest')
    products = Product.query.filter_by(active=True)
    if q:
        products = products.filter(or_(Product.name.ilike(f'%{q}%'), Product.description.ilike(f'%{q}%')))
    if category:
        products = products.filter_by(category=category)
    if sort == 'price_low': products = products.order_by(Product.price.asc())
    elif sort == 'price_high': products = products.order_by(Product.price.desc())
    else: products = products.order_by(Product.created_at.desc())
    categories = [x[0] for x in db.session.query(Product.category).filter_by(active=True).distinct().all()]
    return render_template('shop.html', products=products.all(), q=q, category=category, categories=categories, sort=sort)

@app.get('/product/<int:product_id>')
def product_detail(product_id):
    product = db.get_or_404(Product, product_id)
    if not product.active: abort(404)
    related = Product.query.filter(Product.active.is_(True), Product.category == product.category, Product.id != product.id).limit(4).all()
    return render_template('product.html', product=product, related=related)

@app.post('/cart/add/<int:product_id>')
def cart_add(product_id):
    product = db.get_or_404(Product, product_id)
    sizes = [s.strip() for s in product.sizes.split(',') if s.strip()]
    size = request.form.get('size', '').strip()
    try: qty = int(request.form.get('qty', 1))
    except ValueError: qty = 0
    if not product.active or product.stock < 1 or size not in sizes or qty < 1:
        flash('Choose a valid size and quantity.', 'error')
        return redirect(url_for('product_detail', product_id=product.id))
    cart = dict(session.get('cart', {}))
    key = f'{product.id}:{size}'
    prior = cart.get(key, {}).get('qty', 0)
    cart[key] = {'product_id': product.id, 'size': size, 'qty': min(product.stock, prior + qty)}
    session['cart'] = cart
    flash('Added to your bag.', 'success')
    return redirect(url_for('cart_view'))

@app.get('/cart')
def cart_view():
    items, total = cart_data()
    return render_template('cart.html', items=items, total=total)

@app.post('/cart/update')
def cart_update():
    cart = dict(session.get('cart', {}))
    key = request.form.get('key', '')
    if key in cart:
        try: qty = int(request.form.get('qty', '1'))
        except ValueError: qty = 1
        product = db.session.get(Product, cart[key]['product_id'])
        if qty <= 0 or not product or not product.active: cart.pop(key, None)
        else: cart[key]['qty'] = min(qty, product.stock)
    session['cart'] = cart
    return redirect(url_for('cart_view'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    items, total = cart_data()
    if not items:
        flash('Your bag is empty.', 'error')
        return redirect(url_for('shop'))
    if request.method == 'POST':
        required = {k: request.form.get(k, '').strip() for k in ('customer_name', 'email', 'phone', 'address', 'city', 'country')}
        if any(not x for x in required.values()) or '@' not in required['email']:
            flash('Please complete all required contact and delivery fields.', 'error')
            return render_template('checkout.html', items=items, total=total)
        # Verify stock immediately before checkout; this is a request-to-order flow, not card payment.
        for item in items:
            if item['product'].stock < item['qty']:
                flash('One of your items is no longer available in that quantity.', 'error')
                return redirect(url_for('cart_view'))
        order = Order(**required, postal_code=request.form.get('postal_code', '').strip(), notes=request.form.get('notes', '').strip(), total=total)
        db.session.add(order)
        db.session.flush()
        for item in items:
            p = item['product']
            db.session.add(OrderItem(order_id=order.id, product_id=p.id, product_name=p.name, size=item['size'], qty=item['qty'], price=p.price))
            p.stock -= item['qty']
        db.session.commit()
        session['cart'] = {}
        return redirect(url_for('order_success', order_id=order.id, token=make_order_token(order)))
    return render_template('checkout.html', items=items, total=total)

def make_order_token(order):
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(app.secret_key, salt='orders').dumps({'id': order.id, 'email': order.email})

@app.get('/order-success/<int:order_id>')
def order_success(order_id):
    order = db.get_or_404(Order, order_id)
    from itsdangerous import URLSafeSerializer, BadSignature
    try: data = URLSafeSerializer(app.secret_key, salt='orders').loads(request.args.get('token', ''))
    except BadSignature: abort(403)
    if data != {'id': order.id, 'email': order.email}: abort(403)
    return render_template('success.html', order=order)

@app.get('/about')
def about(): return render_template('about.html')
@app.get('/contact')
def contact(): return render_template('contact.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        admin = Admin.query.filter_by(email=email).first()
        if admin and check_password_hash(admin.password_hash, request.form.get('password', '')):
            session.clear()
            session['admin_id'] = admin.id
            session['_csrf'] = secrets.token_urlsafe(32)
            return redirect(url_for('admin_dashboard'))
        flash('Incorrect email or password.', 'error')
    return render_template('admin_login.html')

@app.post('/admin/logout')
@admin_only
def admin_logout():
    session.clear()
    return redirect(url_for('home'))

@app.get('/admin')
@admin_only
def admin_dashboard():
    orders = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    revenue = db.session.query(db.func.sum(Order.total)).filter(Order.status != 'Cancelled').scalar() or 0
    return render_template('admin_dashboard.html', orders=orders, revenue=revenue, order_count=Order.query.count(), product_count=Product.query.count())

@app.get('/admin/products')
@admin_only
def admin_products():
    return render_template('admin_products.html', products=Product.query.order_by(Product.created_at.desc()).all())

def cloud_enabled():
    return bool(os.getenv('CLOUDINARY_URL'))

def upload_image(file):
    if not file or not file.filename: return ''
    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise ValueError('Only JPG, PNG or WebP images are supported.')
    try:
        image = Image.open(file.stream)
        image.verify()
        file.stream.seek(0)
        image = Image.open(file.stream).convert('RGB')
        image.thumbnail((1600, 1600))
        output = BytesIO()
        image.save(output, 'WEBP', quality=85)
        output.seek(0)
        filename = uuid4().hex
        if cloud_enabled():
            result = cloudinary.uploader.upload(output, folder='step-elegant/products',
                public_id=filename, resource_type='image', format='webp', overwrite=False)
            return result['secure_url']
        local = filename + '.webp'
        (Path(app.config['UPLOAD_FOLDER']) / local).write_bytes(output.read())
        return 'uploads/' + local
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError('Invalid image file.')

def upload_video(file):
    if not file or not file.filename: return ''
    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in ('.mp4', '.webm'):
        raise ValueError('Videos must be MP4 or WebM.')
    stream = file.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size == 0 or size > 40 * 1024 * 1024:
        raise ValueError('Each video must be between 1 byte and 40 MB.')
    header = stream.read(32)
    stream.seek(0)
    if not ((ext == '.mp4' and b'ftyp' in header[4:16]) or
            (ext == '.webm' and header.startswith(b'\x1a\x45\xdf\xa3'))):
        raise ValueError('Video file format does not match its extension.')
    if cloud_enabled():
        result = cloudinary.uploader.upload(stream, folder='step-elegant/products',
            public_id=uuid4().hex, resource_type='video', overwrite=False)
        return result['secure_url']
    filename = uuid4().hex + ext
    dest = Path(app.config['UPLOAD_FOLDER']) / filename
    with dest.open('wb') as target:
        while chunk := stream.read(1024 * 1024):
            target.write(chunk)
    return 'uploads/' + filename

def delete_media(path):
    if path.startswith('https://res.cloudinary.com/') and cloud_enabled():
        # Public ID is derived only from Cloudinary URLs generated by this application.
        from urllib.parse import urlsplit, unquote
        url = urlsplit(path)
        parts = url.path.split('/upload/', 1)
        if len(parts) != 2 or not parts[1].startswith('v'):
            return
        public = parts[1].split('/', 1)[-1].rsplit('.', 1)[0]
        if not public.startswith('step-elegant/products/'):
            return
        kind = 'video' if '/video/upload/' in url.path else 'image'
        cloudinary.uploader.destroy(public, resource_type=kind, invalidate=True)
    elif path.startswith('uploads/'):
        (Path(app.config['UPLOAD_FOLDER']) / Path(path).name).unlink(missing_ok=True)

@app.route('/admin/products/new', methods=['GET', 'POST'])
@app.route('/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
@admin_only
def admin_product_form(product_id=None):
    product = db.get_or_404(Product, product_id) if product_id else None
    if request.method == 'POST':
        created_paths = []
        try:
            data = {'name': request.form.get('name','').strip(), 'category': request.form.get('category','Sneakers').strip(),
                    'description': request.form.get('description','').strip(), 'price': money(request.form.get('price', '')),
                    'compare_price': money(request.form['compare_price']) if request.form.get('compare_price', '').strip() else None,
                    'stock': int(request.form.get('stock', 0)), 'sizes': request.form.get('sizes','').strip(),
                    'active': 'active' in request.form, 'featured': 'featured' in request.form}
            if not data['name'] or not data['category'] or data['stock'] < 0 or not data['sizes']:
                raise ValueError('Name, category, sizes, and non-negative stock are required.')
            existing = list(product.media) if product else []
            removal_ids = set()
            for raw in request.form.getlist('remove_media'):
                try: removal_ids.add(int(raw))
                except ValueError: raise ValueError('Invalid media selection.')
            if removal_ids - {m.id for m in existing}:
                raise ValueError('Invalid media selection.')
            keep = [m for m in existing if m.id not in removal_ids]
            new_images = [v for v in request.files.getlist('images') if v and v.filename]
            new_videos = [v for v in request.files.getlist('videos') if v and v.filename]
            legacy_image = bool(product and product.image and not any(m.kind == 'image' for m in existing))
            legacy_count = 1 if legacy_image else 0
            images_total = sum(m.kind == 'image' for m in keep) + legacy_count + len(new_images)
            videos_total = sum(m.kind == 'video' for m in keep) + len(new_videos)
            if not (1 <= images_total <= 5):
                raise ValueError('Each product must have 1 to 5 images. Select images or keep existing images.')
            if not (0 <= videos_total <= 2):
                raise ValueError('Each product can have 0 to 2 videos.')
            # Check size before accepting any uploads; the request-wide limit is 110 MB.
            for file in new_images:
                file.stream.seek(0, 2)
                size = file.stream.tell()
                file.stream.seek(0)
                if size == 0 or size > 5 * 1024 * 1024:
                    raise ValueError('Each image must be at most 5 MB.')
            new_media = []
            for file in new_images:
                path = upload_image(file)
                created_paths.append(path)
                new_media.append(('image', path))
            for file in new_videos:
                path = upload_video(file)
                created_paths.append(path)
                new_media.append(('video', path))
            if product is None:
                product = Product()
                db.session.add(product)
            for key, val in data.items(): setattr(product, key, val)
            for m in existing:
                if m.id in removal_ids: db.session.delete(m)
            db.session.flush()
            position = max([m.position for m in keep], default=-1) + 1
            if legacy_image:
                db.session.add(ProductMedia(product_id=product.id, kind='image', path=product.image, position=position))
                position += 1
            for kind, path in new_media:
                db.session.add(ProductMedia(product_id=product.id, kind=kind, path=path, position=position))
                position += 1
            # image remains the thumbnail for listings and backwards compatibility.
            final_images = [m.path for m in keep if m.kind == 'image'] + [path for kind, path in new_media if kind == 'image']
            if legacy_image:
                final_images.insert(0, product.image)
            product.image = final_images[0] if final_images else ''
            db.session.commit()
            for m in existing:
                if m.id in removal_ids:
                    try: delete_media(m.path)
                    except Exception: app.logger.exception('Could not remove old media')
            flash('Product and gallery saved.', 'success')
            return redirect(url_for('admin_products'))
        except (ValueError, OverflowError) as err:
            db.session.rollback()
            for path in created_paths:
                try: delete_media(path)
                except Exception: app.logger.exception('Cleanup failed for uploaded media')
            flash(str(err), 'error')
    return render_template('admin_product_form.html', product=product)

@app.post('/admin/products/<int:product_id>/delete')
@admin_only
def admin_product_delete(product_id):
    product = db.get_or_404(Product, product_id)
    # Keep historical order items intact.
    media_paths = [m.path for m in product.media]
    if product.image and product.image not in media_paths: media_paths.append(product.image)
    db.session.delete(product)
    db.session.commit()
    for path in media_paths:
        try: delete_media(path)
        except Exception: app.logger.exception('Could not remove product media')
    flash('Product deleted.', 'success')
    return redirect(url_for('admin_products'))

@app.get('/admin/orders')
@admin_only
def admin_orders():
    return render_template('admin_orders.html', orders=Order.query.order_by(Order.created_at.desc()).all())

@app.route('/admin/orders/<int:order_id>', methods=['GET', 'POST'])
@admin_only
def admin_order_detail(order_id):
    order = db.get_or_404(Order, order_id)
    if request.method == 'POST':
        status = request.form.get('status')
        if status not in ('Pending', 'Confirmed', 'Shipped', 'Delivered', 'Cancelled'): abort(400)
        order.status = status
        db.session.commit()
        flash('Order updated.', 'success')
        return redirect(url_for('admin_order_detail', order_id=order.id))
    return render_template('admin_order_detail.html', order=order)

@app.cli.command('init-db')
def init_db():
    db.create_all()
    print('Database tables created.')

@app.cli.command('create-admin')
def create_admin():
    db.create_all()
    email = os.getenv('ADMIN_EMAIL', '').lower().strip()
    password = os.getenv('ADMIN_PASSWORD', '')
    if not email or len(password) < 12:
        raise RuntimeError('Set ADMIN_EMAIL and a 12+ character ADMIN_PASSWORD in .env first.')
    admin = Admin.query.filter_by(email=email).first()
    if not admin:
        admin = Admin(email=email, password_hash=generate_password_hash(password))
        db.session.add(admin)
        db.session.commit()
        print('Admin created:', email)
    else: print('Admin already exists; password unchanged.')

@app.cli.command('seed-demo')
def seed_demo():
    db.create_all()
    if Product.query.count():
        print('Products already exist; demo seed skipped.')
        return
    data = [
        ('Aero Street Runner','Sneakers',89,'6,7,8,9,10,11',True,'Lightweight everyday sneakers with a clean, contemporary silhouette.'),
        ('Monarch Leather Oxford','Formal',129,'7,8,9,10,11',True,'Classic lace-up elegance in a polished profile.'),
        ('Coastline Low Top','Casual',79,'6,7,8,9,10',True,'Minimal low-top design built for everyday versatility.'),
        ('Velocity Motion','Sports',105,'7,8,9,10,11,12',True,'Responsive cushioning and breathable comfort.'),
        ('Urban Canvas Classic','Casual',65,'6,7,8,9,10,11',False,'An essential companion for laid-back days.'),
        ('Summit Trail Walk','Sports',119,'7,8,9,10,11',False,'Durable, ready-for-anywhere walking comfort.'),
        ('Luxe Derby Noir','Formal',139,'7,8,9,10,11',False,'Refined detailing for elevated occasions.'),
        ('Nova Everyday Knit','Sneakers',95,'6,7,8,9,10,11',False,'Flexible knit upper meets sleek urban styling.'),
    ]
    for name, cat, price, sizes, featured, desc in data:
        db.session.add(Product(name=name, category=cat, price=price, compare_price=price+25, stock=24, sizes=sizes, featured=featured, description=desc))
    db.session.commit()
    print('Eight demo products added. Upload real product photos from admin.')

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG') == '1')
