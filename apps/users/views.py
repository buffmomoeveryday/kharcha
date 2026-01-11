from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib import messages


def login_view(request):  # Renamed to avoid conflict with auth_login
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user_obj = User.objects.filter(email=email).first()
        print(email)

        if user_obj:
            user = authenticate(request, username=user_obj.username, password=password)
            if user is not None:
                auth_login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                return redirect("dashboard")
            else:
                messages.error(request, "Invalid password.")
        else:
            messages.error(request, "No account found with this email.")

    return render(request, "users/login.html")


def registration_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        password2 = request.POST.get("confirm_password")

        if password != password2:
            messages.error(request, "The two passwords do not match.")
            return render(request, "users/registration.html")

        if User.objects.filter(username=username).exists():
            messages.error(request, "This username is already taken.")
            return render(request, "users/registration.html")

        if User.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, "users/registration.html")

        try:
            User.objects.create_user(username=username, email=email, password=password)
            messages.success(
                request, "Account created successfully! You can now login."
            )
            return redirect("login")

        except Exception:
            messages.error(
                request, "An error occurred during registration. Please try again."
            )
            return render(request, "users/registration.html")

    return render(request, "users/registration.html")


def logout_view(request):
    auth_logout(request)
    messages.success(request, "Logged out successfully")
    return redirect("login")
