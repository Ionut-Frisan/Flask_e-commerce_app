from flask import Flask
from os import path
from flask_uploads import IMAGES, UploadSet, configure_uploads
from flask_login import LoginManager

from .views import db

DB_NAME = "database.db"


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = "secret_key_gh"
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'
    app.config['UPLOADED_PHOTOS_DEST'] = 'static/img/'

    db.init_app(app)

    photos = UploadSet("photos",IMAGES)
    configure_uploads(app, photos)

    from website.views import views, Product, User
    from .auth import auth
    

    app.register_blueprint(views, url_prefix="/")
    app.register_blueprint(auth, url_prefix="/")

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    create_database(app, db)

    return app 

def create_database(app, db):
    if not path.exists("website/" + DB_NAME):
        with app.app_context():
            db.create_all(app=app)

app = create_app()