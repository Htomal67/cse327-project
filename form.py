from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length, ValidationError, Email
from flask_bcrypt import Bcrypt
from tables import User


bcrypt = Bcrypt()

class Form(FlaskForm):
    pass

class SignupForm(Form):
    username = StringField(validators=[
                           InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "e.g. NewsReader99"})
    
    email = StringField(validators=[
                        InputRequired(), Email(), Length(max=50)], render_kw={"placeholder": "name@example.com"})

    password = PasswordField(validators=[
                             InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "••••••••"})

    submit = SubmitField('Sign Up')

    def validate_username(self, username): #runs automatically by wtf or by validate on submit
        existing_user_username = User.query.filter_by(
            username=username.data).first()
        if existing_user_username:
            raise ValidationError(
                'That username already exists. Please choose a different one.')

    def validate_email(self, email):
        existing_user_email = User.query.filter_by(
            email=email.data).first()
        if existing_user_email:
            raise ValidationError(
                'That email is already registered.')

  
class LoginForm(Form):
    username = StringField(validators=[
                           InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "Username"})

    password = PasswordField(validators=[
                             InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})

    submit = SubmitField('Login')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if not user:
            raise ValidationError("Username doesn't exist.")

    def validate_password(self, password):
        user = User.query.filter_by(username=self.username.data).first()
        if user:
            if not bcrypt.check_password_hash(user.password, password.data):
                raise ValidationError("Incorrect password.")  
              
              
              
class FormFactory:
    _instance = None 
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FormFactory, cls).__new__(cls) # can't call FormFactory() to prevent recursion
        return cls._instance #singleton
  
    def create_form(self, form_type):
        if form_type == 'login':
            return LoginForm()
        elif form_type == 'signup':
            return SignupForm()
        return None
  