from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    peso = db.Column(db.Float, nullable=True)
    estatura = db.Column(db.Float, nullable=True)
    edad = db.Column(db.Integer, nullable=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "peso": self.peso,
            "estatura": self.estatura,
            "edad": self.edad
        }


class PlanHistory(db.Model):
    """Plan nutricional guardado. Siempre pertenece a un único usuario."""
    __tablename__ = 'plan_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    tipo = db.Column(db.String(20), nullable=False, index=True)  # individual | familiar
    titulo = db.Column(db.String(160), nullable=False)
    resumen = db.Column(db.String(400), nullable=True)
    html = db.Column(db.Text, nullable=False)
    objetivos_json = db.Column(db.Text, nullable=True)
    creado_en = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True
    )

    def to_dict(self, incluir_html=False):
        creado = self.creado_en
        if creado is not None and creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)

        datos = {
            "id": self.id,
            "tipo": self.tipo,
            "titulo": self.titulo,
            "resumen": self.resumen,
            "creado_en": creado.isoformat() if creado else None,
        }
        if incluir_html:
            datos["html"] = self.html
        return datos
