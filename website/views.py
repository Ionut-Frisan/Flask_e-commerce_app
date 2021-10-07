from flask import Blueprint, render_template, request, flash, redirect, url_for, abort, current_app
from flask.globals import session
from werkzeug import useragents
from werkzeug.utils import secure_filename
from wtforms import StringField, IntegerField, TextAreaField
from flask_wtf import FlaskForm
from wtforms import validators
from flask_wtf.file import FileField, FileAllowed
from os import path, makedirs
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_required, current_user
from datetime import datetime
import stripe
import json
import smtplib
from email.message import EmailMessage, Message

order_id = 0
quantities = {}
once = True

EMAIL_ADRESS = "email@email.com"
EMAIL_PASSWORD = "********"

STRIPE_PUBLIC_KEY = "stripe_test_public_key_here"
STRIPE_SCRET_KEY = "stripe_test_secret_key"

stripe.api_key = STRIPE_SCRET_KEY

IMAGES = tuple('jpg jpe jpeg png gif svg bmp raw'.split())

db = SQLAlchemy()

makedirs("website/static/img/", exist_ok=True)

views = Blueprint("views", __name__)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key = True)
    Nume = db.Column(db.String(60))
    PretNou = db.Column(db.Integer)
    PretVechi = db.Column(db.Integer)
    Categorie = db.Column(db.String(50))
    Descriere = db.Column(db.String(1000))
    Cantitate = db.Column(db.Integer)
    Imagini = db.Column(db.String(2000))
    Upload = db.Column(db.Boolean, default=False)

    def __repr__(self) -> str:
        return "ID:" + str(self.id) + " Nume:" + str(self.Nume) + "Pret Nou:" + str(self.PretNou)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key = True)
    username = db.Column(db.String(100), unique=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    admin = db.Column(db.Boolean, default=True, nullable=False)
    phone = db.Column(db.Integer, default = 0)
    orders = db.Column(db.String(1000), default = "")

class AddProduct(FlaskForm):
    Nume = StringField('Nume', validators=[validators.DataRequired()])
    PretNou = IntegerField('PretNout', validators=[validators.DataRequired()])
    PretVechi = IntegerField('PretVechi')
    Categorie = StringField('Categorie', validators=[validators.DataRequired()])
    Descriere = TextAreaField('Descriere', validators=[validators.DataRequired()])
    Cantitate = IntegerField("Cantitate", validators=[validators.DataRequired()])
    Upload = IntegerField("Upload", validators=[validators.DataRequired(), validators.NumberRange(min=0, max=1, message="1-Necesita upload")])
    Imagini = FileField('Imagine', validators=[FileAllowed(IMAGES, 'Only images are accepted.')])

class Order(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    #user_id = -1 -> client not logged in/doesn't have account, user id otherwise
    user_id = db.Column(db.Integer)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    adress = db.Column(db.String(200))
    details = db.Column(db.String(1000))
    payment = db.Column(db.String(10))
    products = db.Column(db.String(10000))
    date = db.Column(db.String(80))
    payment_id = db.Column(db.String(150), default = "")
    total = db.Column(db.Integer, default=0)
    #status = 0 -> products were added to cart, but no order was placed yet;
    #            1 -> the order was placed but it was not delivered yet
    #            2 -> the order was placed, processed and delivered
    #           -1 -> the payment was not processed
    #           -2 -> cancelled order 
    status = db.Column(db.Integer, default=0)

class Interaction(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key = True)
    title = db.Column(db.String(150))
    email = db.Column(db.String(50))
    message = db.Column(db.String(1000))
    date = db.Column(db.String(80))

    def __str__(self) -> str:
        return f"id: {self.id}, title: {self.title}, email: {self.email}, message: {self.message}, date: {self.date} \n"

def get_email():
    print(session)
    if not session.get("Checkout") is None:
        return session["Checkout"]["email"]
    else:
        return "ionutfrisan@gmail.com"

def get_name():
    return session["Checkout"]["first_name"]

def get_order():
    return session["Checkout"]["order_id"]


def send_mail():
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()

        smtp.login(EMAIL_ADRESS, EMAIL_PASSWORD)

        msg = EmailMessage()

        msg["Subject"] = "WhyNot.co.uk Order"
        msg["From"] = EMAIL_ADRESS
        msg["To"] = get_email()
        msg.set_content(f"Hello {get_name()}, we received order {get_order()}.\n First of all we would like you thank you for choosing us! \nYour order will be shipped as soon as possible and you will be notified as soon as the product is ready to be sent.\n If you have any questions you can reach us at contact.whynot.com@gmail.com ")
        msg.add_alternative(f"""\
            <!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mail</title>
</head>
<body>
    <h3 class="greet" style="font-size: 24px;color: rgb(255, 94, 0);text-align: center;">Hello {get_name()}, we received order {get_order()}.</h3>
    <p class="thanks" style="font-size: 18px;color: rgb(51,51,51);text-align: center;"> First of all we would like you thank you for choosing us!</p>
    <p class="info" style="font-size: 18px;color: rgb(51,51,51);text-align: center;"> Your order will be shipped as soon as possible and you will be notified as soon as the product is ready to be sent. </p>
    <p class="contact" style="font-size: 14px;color: rgb(51,51,51);text-align: center;"> If you have any questions you can reach us at contact.whynot.com@gmail.com </p>
</body>
</html>
""", subtype="html")

        smtp.send_message(msg)

def allowed_files(filename):
    #verifies if the file passed is an image, returns a bool
    return "." in filename and filename.rsplit(".",1)[1].lower() in IMAGES

def calculate_total_pay():
    #calculates the total the client has to pay for the open order, returns int
    total = 0
    for key, value in session["ShoppingCart"].items():
        total = total + int(value["quantity"])*int(value["price"])
    return total

def generate_name():
    #generates the name of the products that will appear on the payment page
    name = ""
    for key, value in session["ShoppingCart"].items():
        name = name + str(value["quantity"]) + " * " + value["name"][0:20] + ",\n"
    return name[:-2]

@views.route("/stripe_pay", methods=["POST"])
def stripe_pay():
    #redirects client to the payment page, takes values from app session
    sessionn = stripe.checkout.Session.create(
    payment_method_types=['card'],
    line_items=[{
      'price_data': {
        'currency': 'gbp',
        'product_data': {
          'name': generate_name(),
        },
        'unit_amount': calculate_total_pay(),
      },
      'quantity': 1,
      
    }],
    mode='payment',
    success_url=url_for("views.success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
    cancel_url=url_for("views.home", _external=True),
  )
    session.pop("ShoppingCart", None)
    return redirect(sessionn.url, code=303)

def update_order_after_hook(status, payment_intent):
    global order_id, session, quantities, once
    if once == True or int(status) == 1 or payment_intent != "":
        order = Order.query.filter_by(id=int(order_id)).first()
        if int(status) == 1:
            order.status = status
        if (payment_intent != ""):
            order.payment_id = payment_intent
        db.session.commit()
    if once:
        for key, value in quantities.items():
            try:
                product = Product.query.filter_by(id=int(key)).first()
                product.Cantitate = product.Cantitate - int(value)  
                db.session.commit()               
            except:
                print("eroare la query in Product!")
    once = False

@views.route("/stripe_webhook", methods=["POST"])
def stripe_webhook():
    #checks if the payment has been succesfully processed,
    #changes the order status accordingly
    if request.content_length > 1024*1024: 
        print("REQUEST TOO BIG")
        abort(400)
    
    print(" *** Webhook has been called! *** ")

    payload = request.get_data()
    sig_header = request.environ.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = "whsec_DWiRIIEZLUzhCX19bJPMU9396jIlZLDa"
    event = None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as ve:
        print("INVALID PAYLOAD")
        return {}, 400
    except:
        print("INVALID SIGNATURE")
        return {}, 400 

    if event["type"] == "checkout.session.completed":
        sessionn = event["data"]["object"]
        payment_intent = sessionn["payment_intent"]
        print(f"Payment intent in webhook: {payment_intent}")
        update_order_after_hook(1, payment_intent)
    else:
        update_order_after_hook(-2, "")
    return {}

@views.route("/succ")
def succ():
    return render_template("success.html", user=current_user)

@views.route("/success")
def success():
    send_mail()
    return render_template("success.html", user=current_user)

@views.route("/admind")
@login_required
def admin():
    if current_user.admin == True:
        return render_template("admind.html")
    else:
        return redirect(url_for("views.home"), user=current_user)

@views.route("/admind/produse/delete/<int:id>", methods=["GET", "POST"])
@login_required
def stergere_produs(id):
    if current_user.admin == True:
        produs_sters = Product.query.get_or_404(id)
        try:
            db.session.delete(produs_sters)
            db.session.commit()
            flash("Produsul a fost sters cu succes!")
            return redirect(url_for("views.vizualizare_produse"))
        except:
            flash("Ooops... ceva nu a functionat conform demersului gandit de echipa tehnica :( Incercati mai tarziu sau sunati-l pe Frisu hahahaha")
            return redirect(url_for("views.vizualizare_produse"))
    else:
        flash("You dont\'t have the access in that section of the website!",category="error")
        return redirect(url_for("views.home", user=current_user))

@views.route("/admind/produse/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_produs(id):
    if current_user.admin == True:
        produs_editat = Product.query.get_or_404(id)
        if request.method == "POST":
            numeNou = request.form["nume"]
            pretActualizat = request.form["pretActualizat"]
            pretVechi = request.form["pretVechi"]
            cantitateNoua = request.form["cantitate"]
            descriereNoua = request.form["descriere"]
            categorieNoua = request.form["categorie"]
            uploadNou = request.form["upload"]

            if len(numeNou) > 0 :
                produs_editat.Nume = numeNou
            if len(pretActualizat) > 0 :
                produs_editat.PretNou = int(pretActualizat)
            if len(pretVechi) > 0:
                produs_editat.PretVechi = int(pretVechi)
            if len(cantitateNoua) > 0 :
                produs_editat.Cantitate = int(cantitateNoua)
            if len(descriereNoua) > 0 : 
                produs_editat.Descriere = descriereNoua
            if len(categorieNoua) > 0 :
                produs_editat.Categorie = categorieNoua
            if len(uploadNou) > 0 :
                produs_editat.Upload = int(uploadNou)
            try:
                db.session.commit()
            except:
                return "S-a produs o eroare"
            flash("Modificarile s-au efectuat cu succes!")
            return redirect(url_for("views.vizualizare_produse"))
        else:
            return render_template("edit_product.html", produs_editat = produs_editat)
    else:
        flash("You dont\'t have the access in that section of the website!",category="error")
        return redirect(url_for("views.home", user=current_user))
            
@views.route("/admind/produse/vizualizare", methods=["GET", "POST"], defaults={"page": 1})
@views.route("/admind/produse/vizualizare/<int:page>", methods=["GET", "POST"])
@login_required
def vizualizare_produse(page):
    if current_user.admin == True:
        try:
            page=page
            pages = 20
            products = Product.query.order_by(Product.id.asc()).paginate(page, pages, error_out=False)
            if request.method == "POST" and "tag" in request.form and len(request.form["tag"]) > 0:
                tag = request.form["tag"]
                search = "{}".format(tag)
                try:
                    search = int(search)
                    products = Product.query.filter(Product.id.like(f"%{search}%")).paginate(page, pages, error_out=False)
                except:
                    products = Product.query.filter(Product.Nume.like(f"%{search}%")).paginate(page, pages, error_out=False)
                return render_template("view_products.html", products=products, tag=search)
            elif request.method == "POST" and len(request.form["tag"]) == 0:
                products = Product.query.order_by(Product.id.asc()).paginate(page, pages, error_out=False)
                return render_template("view_products.html", products=products, tag="")
            return render_template("view_products.html", products=products, tag="")
        except:
            flash("A aparut o eroare, va rugam sa incercati mai tarziu", category="error")
            return redirect(request.referrer)
    else:
        #flash("You dont\'t have the access in that section of the website!",category="error")
        return redirect(url_for("views.home", user=current_user))

@views.route("/admind/produse/add", methods=['GET','POST'])
@login_required
def add_produse():
    if current_user.admin == True:
        form = AddProduct()
        if request.method == "POST":
            nume = request.form.get("Nume")
            pretNou = request.form.get("PretNou")
            pretVechi = request.form.get("PretVechi")
            categorie = request.form.get("Categorie")
            descriere = request.form.get("Descriere")
            cantitate = request.form.get("Cantitate")
            upload = request.form.get("Upload")
            upload = int(upload)

            if 'files[]' not in request.files:
                flash("Nu ati selectat imagine")

            Imagini = request.files.getlist("files[]")

            for Imagine in Imagini:
                if Imagine.filename == "":
                    flash("NU ati selectat imagine")

            saved_images = 0
            files = ""
            for Imagine in Imagini:
                if Imagine and allowed_files(Imagine.filename):
                    filename = secure_filename(Imagine.filename)
                    files = files + filename + "//"
                    Imagine.save(path.join("website/static/img/", filename))
                    saved_images += 1
            
            if saved_images > 0 and saved_images <= 3:
                flash("Produsul a fost adaugat cu succes!", "info")
                product = Product(Nume=nume, PretNou=pretNou, PretVechi=pretVechi, Categorie=categorie, Descriere=descriere, Cantitate=cantitate, Imagini=files, Upload=upload)

                db.session.add(product)
                db.session.commit()
            else:
                flash("Formatul imagini(lor) nu este acceptat sau ati incarcat prea multe imagini (0 < nr imagini <= 3) !", "error")

        return render_template("add_produse.html", form=form)
    else:
        flash("You dont\'t have the access in that section of the website!",category="error")
        return redirect(url_for("views.home", user=current_user))

@views.route("/home/", methods=['POST', "GET"])
@views.route("/", methods=['POST', "GET"])
def home():
    keyword = "Insert keyword"
    products = Product.query.all()
    if request.method == "POST" and "tag" in request.form and len(request.form["tag"]) > 0:
        tag = request.form["tag"]
        search = "{}".format(tag)
        products = Product.query.filter(Product.Nume.like(f"%{search}%")).all()
        keyword = "Search result for: "+search
    return render_template("home.html", products=products, user=current_user, keyword=keyword)


@views.route("/product/product_code=<id>", methods=["POST", "GET"])
def product(id):
    if request.method == "POST" and "tag" in request.form and len(request.form["tag"]) > 0:
        tag = request.form["tag"]
        search = "{}".format(tag)
        products = Product.query.filter(Product.Nume.like(f"%{search}%")).all()
        keyword = "Search result for: "+search
        #products = Product.query.filter(Product.Nume == search).paginate(page, pages, error_out=False)
        return render_template("home.html", products=products, user=current_user, keyword=keyword)
    product = Product.query.filter_by(id=id).first()
    imagini = product.Imagini
    imagini = imagini.split("//")
    return render_template("product.html", product=product, imagini=imagini, user=current_user)

def mergeDicts(dict1, dict2):
    if isinstance(dict1, list) and isinstance(dict2, list):
        return dict1+dict2
    elif isinstance(dict1, dict) and isinstance(dict2, dict):
        return dict(list(dict1.items()) + list(dict2.items()))
    return "False"

@views.route("/addcart", methods=["POST"])
def addCart():

    quantity = request.form.get("quantity")
    product_id = request.form.get("product_id")
    product = Product.query.filter_by(id=product_id).first()
    if product.Upload == True:
        if 'files[]' not in request.files:
            flash("Please select at least one image")
            return redirect(request.referrer)


        Imagini = request.files.getlist("files[]")

        cnt = 0
        for Imagine in Imagini:
            if Imagine.filename == "":
                flash("You added an invalid image")
            cnt += 1

        if cnt > int(quantity):
            flash(f"You can upload a maximum of {quantity} images.")
            return redirect(request.referrer)
        elif cnt == 0:
            flash("Please upload at leas one image!")
            return redirect(request.referrer)

        saved_images =0
        files = ""

        for Imagine in Imagini:
            if Imagine and allowed_files(Imagine.filename):
                filename = secure_filename(Imagine.filename)
                files = files + filename + "//"
                flash("A b c ")
                Imagine.save(path.join("website/static/order_img/", filename))
                flash("D e f")
                saved_images += 1

    if product_id and quantity and request.method == "POST":
        DictItems = {product_id:{"name": product.Nume, "price": product.PretNou, "quantity": quantity, "description": product.Descriere}}
        if "ShoppingCart" in session:
            if product_id not in session["ShoppingCart"]:
                session["ShoppingCart"] = mergeDicts(session["ShoppingCart"], DictItems)
                flash(str(session["ShoppingCart"]))
                flash("Product has been added to cart! You can keep shooping :)")
                return redirect(request.referrer)
            else:
                items = {}
                item={}
                for key, value in session["ShoppingCart"][product_id].items():
                    return 1
                return items
                items += {"name": product.Nume, "price": product.PretNou, "quantity": quantity, "description": product.Descriere}
                session["ShoppingCart"][product_id] = items
        else:
            session["ShoppingCart"] = DictItems
            flash("Product has been added to cart! You can keep shooping :)")
            return redirect(request.referrer)    


@views.route("/cart", methods=["POST", "GET"])
def getCart():
    if request.method == "POST" and "tag" in request.form and len(request.form["tag"]) > 0:
        tag = request.form["tag"]
        search = "{}".format(tag)
        products = Product.query.filter(Product.Nume.like(f"%{search}%")).all()
        keyword = "Search result for: "+search
        #products = Product.query.filter(Product.Nume == search).paginate(page, pages, error_out=False)
        return render_template("home.html", products=products, user=current_user, keyword=keyword)
    if "ShoppingCart" not in session:
        return render_template("view_cart.html", user=current_user, Product=Product)
    return render_template("view_cart.html", user=current_user, Product=Product)

@views.route("/updatecart/update_cart_product_code=<id>", methods=["POST", "GET"])
def updateCart(id):
    if "ShoppingCart" not in session and len(session["ShoppingCart"]) <= 0 :
        return redirect(url_for("views.home"))
    if request.method == "POST" :
        quantity = request.form.get("quantity")
        try:
            session.modified = True
            for key, item in session["ShoppingCart"].items():
                if int(key) == int(id):
                    item["quantity"] = quantity
                    flash("Item is updated", category="succes")
                    return redirect(url_for("views.getCart"))
        except Exception as e:
            print(e)
            return redirect(url_for("views.getCart"))


@views.route("/removeItemFromCart/product_code=<id>")
def deleteItem(id):
    if "ShoppingCart" not in session and len(session["ShoppingCart"]):
        return redirect(url_for("views.home"))
    try:
        session.modified = True
        for key, item in session["ShoppingCart"].items():
            if int(key) == int(id):
                session["ShoppingCart"].pop(key, None)
                flash("Item deleted succesfully", category="succes")
                return redirect(url_for("views.getCart"))
    except Exception as e:
        print(e)
        return redirect(url_for("views.getCart"))

@views.route("/clearcart")
def clearCart():
    try:
        session.pop("ShoppingCart", None)
        if "cart" in request.referrer:
            flash("Cart was cleared succesfully", category="succes")
        return redirect(url_for("views.home"))
    except Exception as e:
        print(e)
        flash("An error has occured while clearing cart!", category="error")
        return redirect(request.referrer)


def checkCart():
    ok = True
    
    for key, value in session["ShoppingCart"].items():
        product = Product.query.filter_by(id=key).first()
        if int(value["quantity"]) > int(product.Cantitate):
            session["ShoppingCart"][str(product.id)]["quantity"] = product.Cantitate
            ok = False
        if int(value["price"]) != int(product.PretNou):
            session["ShoppingCart"][str(product.id)]["price"] = product.PretNou
            ok = False
    return ok


@views.route("/checkout", methods=["POST", "GET"])
def checkout():
    global order_id, quantities
    try:
        if checkCart() == False:
            flash("Your cart contained invalid data, it was updated automatically so please check the contents!", category="error")
            return redirect(url_for("views.getCart"))
    except :
        flash("One of the products is no longer in our depository! Please update the cart!", category="error")
        return redirect(url_for("views.getCart"))
    if request.method == "POST" and checkCart:
        firstName = request.form.get("firstName")
        lastName = request.form.get("lastName")
        email = request.form.get("email")
        phone = request.form.get("phone")
        city = request.form.get("city")
        street = request.form.get("street")
        apartament = request.form.get("apartament")
        zipCode = request.form.get("zip")
        details = request.form.get("textarea")
        payment = request.form.get("pay")

        if current_user.is_authenticated:
            user_id = current_user.id
        else:
            user_id = -1

        adress = city + ", " + street + ", ap " + apartament + ", " + zipCode
        name = firstName +" "+ lastName

        dtime = datetime.now()
        if(dtime.hour < 10): hour = ("0") + str(dtime.hour)
        else:hour=str(dtime.hour)
        if(dtime.minute < 10): minute = ("0") + str(dtime.minute)
        else: minute=str(dtime.minute)
        date = str(dtime.year) + "/" + str(dtime.month) + "/" + str(dtime.day) + ", " + hour + ":" + minute
        products = json.dumps(session["ShoppingCart"])
        total = calculate_total_pay()

        order = Order(user_id=user_id, name=name, email=email, phone=phone, adress=adress, details=details, payment=payment, date=date, status=0, total=total, products=products)
        db.session.add(order)
        db.session.commit()

        order_id = order.id
        for key, value in session["ShoppingCart"].items():
            quantities[key] = value["quantity"]

        CheckoutDetails = {"order_id":order_id, "first_name":firstName, "last_Name": lastName, "email": email, "phone": phone,
                     "city": city, "street": street, "apartament": apartament, "zip":zipCode, "details": details, "total": total}

        session["Checkout"] = CheckoutDetails

        if payment == "Credit/Debit Card":
            return redirect(url_for("views.stripe_pay"), code=307)
        else:
            session.pop("ShoppingCart", None)
            return redirect(url_for("views.success"))
    else: 
        return render_template("checkout.html", user=current_user)


@views.route("/admind/view_orders/<int:page>",methods=["POST", "GET"])
@login_required
def viewOrders(page):
    if current_user.admin == True:
        page=page
        pages = 50
        orders = Order.query.paginate(page, pages, error_out=False)

        if request.method == "POST" and "tag" in request.form and len(request.form.get("tag")) > 0:
            tag = request.form.get("tag")
            search = "{}".format(tag)
            criteria = request.form.get("criteria")
            orders = Order.query.filter(Order.__getattribute__(Order, f"{criteria}").like(f"%{search}%")).paginate(page, pages, error_out=False)
            return render_template("view_orders.html",orders=orders,tag=tag)
        elif request.method == "POST" and len(request.form.get("tag")) == 0:
            orders = Order.query.order_by(Order.id.asc()).paginate(page,pages,error_out=False)
            return render_template("view_orders.html", orders=orders, tag="")
        return render_template("view_orders.html", orders=orders, tag="")

@views.route("/admind/view_order/id=<order_id>")
@login_required
def view_order(order_id):
    if current_user.admin == True:
        order = Order.query.filter_by(id=order_id).first()
        products = order.products
        products = json.loads(products)
        return render_template("view_order.html", order=order, products=products)
    else:
        return redirect(url_for("views.home"), user=current_user)

@views.route("/cancel_order/id=<order_id>")
def cancel_order(order_id):
    if current_user.admin == True:
        try:
            order = Order.query.filter_by(id=order_id).first()
            if order.status == 1 or order.status == 2:
                order.status = -1 
                flash("Orderul a fost anulat cu succes!", category="succes")
            elif order.status == -1:
                flash("Orderul este deja anulat!", category="error")
            else:
                flash("Acest tip de order nu poate fi anulat!", category="error")
        except:
            flash("A aparut o eroare, incearca mai tarziu!", category="error")
    db.session.commit()
    return redirect(request.referrer)

@views.route("/finalize_order/id=<order_id>")
def finalize_order(order_id):
    if current_user.admin == True:
        try:
            order = Order.query.filter_by(id=order_id).first()
            if order.status == 1 :
                order.status = 2
                flash("Orderul a fost marcat ca 'finalizat' cu succes", category="succes")
            elif order.status == 2:
                flash("Acest order este deja marcat ca 'finalizat' !", category="error")
            else:
                flash("Acest order nu poate fi marcat ca 'finalizat' !", category="error")
        except:
            flash("A aparut o eroare, incercati mai tarziu!", category="error")
    db.session.commit()
    return redirect(request.referrer)

@views.route("/contact", methods=["POST", "GET"])
def contact():
    if request.method == "POST":

        title = request.form.get("title")
        email = request.form.get("email")
        message = request.form.get("message")
        dtime = datetime.now()
        if(dtime.hour < 10): hour = ("0") + str(dtime.hour)
        else:hour=str(dtime.hour)
        if(dtime.minute < 10): minute = ("0") + str(dtime.minute)
        else: minute=str(dtime.minute)
        date = str(dtime.year) + "/" + str(dtime.month) + "/" + str(dtime.day) + ", " + hour + ":" + minute
        contact = Interaction(title=title, email=email, message=message, date=date)
        db.session.add(contact)
        db.session.commit()
        flash("Message has been sent! We will get back at you as soon as possible.", category="success")

    return render_template("contact.html", user=current_user)

@views.route("/admind/view_interactions")
def view_interactions():
    interactions = Interaction.query.all()
    return render_template("view_interactions.html", interactions=interactions)

@views.route("/admind/view_interaction/id=<id>")
def view_interaction(id):
    interaction = Interaction.query.filter_by(id=id).first()
    return render_template("view_interaction.html", interaction=interaction)

"""
@views.route("/home/payments")
def payments():
    list = stripe.PaymentIntent.list(limit=100)
    return list
"""