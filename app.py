
from website import create_app 
from flask_session import Session

if __name__ == "__main__":
    app = create_app()
    SECRET_KEY = "changeme"
    SESSION_TYPE = 'filesystem'
    app.config.from_object(__name__)
    #Session(app)
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    app.run(debug=True, port=5000)

