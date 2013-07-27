from flask import Flask
import config

app = Flask(__name__)
app.config.from_object(config)

from fm.tags.views import mod as tagsModule
app.register_blueprint(tagsModule)
