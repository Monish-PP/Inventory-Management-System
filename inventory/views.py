from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.db.models import Sum
from .forms import CustomUserCreationForm
from .models import Item, Purchase, Sale, EmailOTP
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO
from django.http import HttpResponse
from datetime import datetime


def user_login(request):
    if request.method == "POST":
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("inventory:home")
        else:
            if form.errors:
                if form.non_field_errors():
                    messages.error(request, str(form.non_field_errors()[0]))
                else:
                    error_fields = ", ".join(
                        [
                            f"{k}: {v[0]}"
                            for k, v in form.errors.items()
                            if k != "__all__"
                        ]
                    )
                    messages.error(
                        request, f'Login error: {error_fields or "Check credentials"}'
                    )
            else:
                messages.error(request, "Invalid login")
    else:
        form = AuthenticationForm()
    return render(request, "login.html", {"form": form})


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            username = form.cleaned_data.get("username")
            email = form.cleaned_data.get("email")

            # Generate 6-digit OTP
            otp_code = str(random.randint(100000, 999999))
            EmailOTP.objects.update_or_create(user=user, defaults={"otp": otp_code})

            # Send OTP email
            subject = "Your Verification Code - Inventory Management System"
            message = render_to_string(
                "email/otp_email.txt",
                {"user": user, "otp": otp_code},
            )
            html_message = render_to_string(
                "email/otp_email.html",
                {"user": user, "otp": otp_code},
            )
            try:
                send_mail(
                    subject,
                    message,
                    None,
                    [email],
                    html_message=html_message,
                    fail_silently=False,
                )
                messages.success(
                    request,
                    f"Account created for {username}! Please check your email ({email}) for the 6-digit OTP code.",
                )
            except Exception as e:
                messages.warning(
                    request,
                    f"Account created for {username}, but we could not send the OTP email. "
                    f"Please ask the administrator to check the email settings. Error: {e}",
                )
            request.session["otp_user_id"] = user.id
            return redirect("inventory:verify_otp")
        else:
            if "username" in form.errors:
                messages.error(request, "Username taken")
            elif "email" in form.errors:
                messages.error(request, "Email error: " + str(form.errors["email"][0]))
            elif "password2" in form.errors:
                messages.error(request, "Passwords mismatch")
            elif form.non_field_errors() or "__all__" in form.errors:
                messages.error(request, "Registration error")
            else:
                messages.error(request, "Fix errors")
    else:
        form = CustomUserCreationForm()
    return render(request, "register.html", {"form": form})


def verify_otp(request):
    user_id = request.session.get("otp_user_id")
    if not user_id:
        messages.error(request, "Session expired. Please register again.")
        return redirect("inventory:register")

    user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        entered_otp = request.POST.get("otp", "")
        try:
            otp_record = EmailOTP.objects.get(user=user)
            if otp_record.otp == entered_otp:
                user.is_active = True
                user.save()
                otp_record.delete()
                del request.session["otp_user_id"]
                messages.success(
                    request, "Email verified successfully! You can now log in."
                )
                return redirect("inventory:login")
            else:
                messages.error(request, "Invalid OTP. Please try again.")
        except EmailOTP.DoesNotExist:
            messages.error(request, "OTP expired. Please register again.")
            return redirect("inventory:register")

    return render(request, "verify_otp.html", {"email": user.email})


@login_required
def user_logout(request):
    logout(request)
    messages.success(request, "Logged out successfully!")
    return redirect("inventory:home")


@login_required
def home(request):
    items = Item.objects.all()
    total_items = items.count()
    total_stock = items.aggregate(Sum("quantity"))["quantity__sum"] or 0
    total_sales = Sale.objects.aggregate(Sum("quantity"))["quantity__sum"] or 0
    total_purchases = Purchase.objects.aggregate(Sum("quantity"))["quantity__sum"] or 0
    low_stock = items.filter(quantity__lt=10)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context = {
        "items": items,
        "total_items": total_items,
        "total_stock": total_stock,
        "total_sales": total_sales,
        "total_purchases": total_purchases,
        "low_stock": low_stock,
        "current_time": current_time,
    }
    return render(request, "home.html", context)


@login_required
def add_item(request):
    if request.method == "POST":
        name = request.POST["name"]
        quantity = int(request.POST["quantity"])
        price = float(request.POST["price"])
        Item.objects.create(name=name, quantity=quantity, price=price)
        messages.success(request, "Item added successfully!")
        return redirect("inventory:home")
    return render(request, "add_item.html")


@login_required
def purchase_item(request):
    items = Item.objects.all()
    if request.method == "POST":
        item_id = request.POST["item"]
        quantity = int(request.POST["quantity"])
        item = get_object_or_404(Item, id=item_id)
        item.quantity += quantity
        item.save()
        Purchase.objects.create(item=item, quantity=quantity)
        messages.success(request, f"Purchased {quantity} of {item.name}")
        return redirect("inventory:home")
    return render(request, "purchase.html", {"items": items})


@login_required
def sell_item(request):
    items = Item.objects.all()
    if request.method == "POST":
        item_id = request.POST["item"]
        quantity = int(request.POST["quantity"])
        item = get_object_or_404(Item, id=item_id)
        if item.quantity >= quantity:
            item.quantity -= quantity
            item.save()
            Sale.objects.create(item=item, quantity=quantity)
            messages.success(request, f"Sold {quantity} of {item.name}")
        else:
            messages.error(request, f"Not enough stock! Available: {item.quantity}")
        return redirect("inventory:home")
    return render(request, "sale.html", {"items": items})


@login_required
def pdf_reports(request):
    date_format = request.GET.get("date_format", "12hr")  # default 12hr
    """Generate PDF report of stock operations"""
    # Same data as reports view
    total_purchases_qty = (
        Purchase.objects.aggregate(Sum("quantity"))["quantity__sum"] or 0
    )
    total_sales_qty = Sale.objects.aggregate(Sum("quantity"))["quantity__sum"] or 0
    total_transactions = total_purchases_qty + total_sales_qty
    net_stock_change = total_purchases_qty - total_sales_qty

    # Get combined recent transactions (last 10 most recent across purchases & sales)
    all_transactions = list(
        Purchase.objects.select_related("item").order_by("-date")[:10]
    ) + list(Sale.objects.select_related("item").order_by("-date")[:10])
    all_transactions.sort(key=lambda t: t.date, reverse=True)
    recent_transactions = all_transactions[:10]

    header_date = "#"
    transactions_data = []
    for t in recent_transactions:
        type_str = (
            "Purchase"
            if hasattr(t, "quantity") and hasattr(t.item, "purchases")
            else "Sale"
        )
        if date_format == "none":
            date_str = ""
        elif date_format == "12hr":
            date_str = t.date.strftime("%B %d, %Y - %I:%M %p")
            header_date = "Date"
        else:  # 24hr
            date_str = t.date.strftime("%B %d, %Y - %H:%M")
            header_date = "Date (24hr)"
        transactions_data.append([date_str, type_str, t.item.name, t.quantity])

    item_stats = {}
    for p in Purchase.objects.select_related("item"):
        name = p.item.name
        item_stats[name] = item_stats.get(name, {"purchased": 0, "sold": 0})
        item_stats[name]["purchased"] += p.quantity
    for s in Sale.objects.select_related("item"):
        name = s.item.name
        item_stats[name] = item_stats.get(name, {"purchased": 0, "sold": 0})
        item_stats[name]["sold"] += s.quantity

    item_summary_data = []
    for name, stats in sorted(
        item_stats.items(), key=lambda x: x[1]["purchased"], reverse=True
    )[:10]:
        net = stats["purchased"] - stats.get("sold", 0)
        item_summary_data.append([name, stats["purchased"], stats.get("sold", 0), net])

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()

    story = []

    # Title
    title = Paragraph(
        "Inventory Management System - Stock Operations Report", styles["Title"]
    )
    story.append(title)
    story.append(Spacer(1, 12))

    # Summary table
    summary_data = [
        ["Metric", "Value"],
        ["Total Transactions", total_transactions],
        ["Total Purchases", total_purchases_qty],
        ["Total Sales", total_sales_qty],
        ["Net Stock Change", net_stock_change],
    ]
    summary_table = Table(summary_data)
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 14),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (0, -1), colors.beige),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 12))

    # Recent transactions
    transactions_header = Paragraph("Recent Transactions (Last 5)", styles["Heading2"])
    story.append(transactions_header)
    if transactions_data:
        trans_table = Table(
            [[header_date, "Type", "Item", "Qty"]] + transactions_data[:10]
        )
        trans_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(trans_table)
    else:
        story.append(Paragraph("No transactions found.", styles["Normal"]))

    story.append(Spacer(1, 12))

    # Item summary
    item_header = Paragraph("Top 10 Items Summary", styles["Heading2"])
    story.append(item_header)
    if item_summary_data:
        item_table = Table([["Item", "Purchased", "Sold", "Net"]] + item_summary_data)
        item_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )
        story.append(item_table)
    else:
        story.append(Paragraph("No item data available.", styles["Normal"]))

    story.append(Spacer(1, 12))

    # Footer
    footer = Paragraph(
        f"Report generated: {datetime.now().strftime('%B %d, %Y - %I:%M %p')}",
        styles["Normal"],
    )
    story.append(footer)

    doc.build(story)

    # Email PDF to registered user
    if request.user.is_authenticated and request.user.email:
        try:
            email = EmailMessage(
                subject="Your Inventory Report",
                body=(
                    f"Hi {request.user.username},\n\n"
                    f"Please find your requested inventory report attached.\n\n"
                    f"Generated on: {datetime.now().strftime('%B %d, %Y - %I:%M %p')}"
                ),
                from_email=None,
                to=[request.user.email],
            )
            email.attach("inventory_report.pdf", buffer.getvalue(), "application/pdf")
            email.send()
            messages.success(
                request, "Report has been emailed to your registered email address."
            )
        except Exception as e:
            messages.warning(request, f"Could not email the report: {e}")

    buffer.seek(0)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="inventory_report.pdf"'
    return response


@login_required
def reports(request):
    total_purchases_qty = (
        Purchase.objects.aggregate(Sum("quantity"))["quantity__sum"] or 0
    )
    total_sales_qty = Sale.objects.aggregate(Sum("quantity"))["quantity__sum"] or 0
    net_stock_change = total_purchases_qty - total_sales_qty

    recent_purchases = Purchase.objects.select_related("item").order_by("-date")[:5]
    recent_sales = Sale.objects.select_related("item").order_by("-date")[:5]
    recent_transactions = []
    for p in recent_purchases:
        recent_transactions.append(
            {
                "date": p.date,
                "type": "Purchase",
                "item": p.item.name,
                "quantity": p.quantity,
            }
        )
    for s in recent_sales:
        recent_transactions.append(
            {
                "date": s.date,
                "type": "Sale",
                "item": s.item.name,
                "quantity": s.quantity,
            }
        )
    recent_transactions.sort(key=lambda x: x["date"], reverse=True)

    all_purchases = Purchase.objects.select_related("item").order_by("-date")[:20]
    all_sales = Sale.objects.select_related("item").order_by("-date")[:20]
    all_transactions = []
    for p in all_purchases:
        all_transactions.append(
            {
                "date": p.date,
                "type": "Purchase",
                "item": p.item.name,
                "quantity": p.quantity,
            }
        )
    for s in all_sales:
        all_transactions.append(
            {
                "date": s.date,
                "type": "Sale",
                "item": s.item.name,
                "quantity": s.quantity,
            }
        )

    item_stats = {}
    for p in Purchase.objects.select_related("item"):
        name = p.item.name
        item_stats[name] = item_stats.get(name, {"purchased": 0, "sold": 0})
        item_stats[name]["purchased"] += p.quantity
    for s in Sale.objects.select_related("item"):
        name = s.item.name
        item_stats[name] = item_stats.get(name, {"purchased": 0, "sold": 0})
        item_stats[name]["sold"] += s.quantity

    item_summary = []
    for name, stats in sorted(
        item_stats.items(), key=lambda x: x[1]["purchased"], reverse=True
    ):
        net = stats["purchased"] - stats.get("sold", 0)
        item_summary.append(
            {
                "item__name": name,
                "total_purchased": stats["purchased"],
                "total_sold": stats.get("sold", 0),
                "net_change": net,
            }
        )

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context = {
        "all_transactions": all_transactions,
        "recent_transactions": recent_transactions[:10],
        "total_transactions": total_purchases_qty + total_sales_qty,
        "total_purchases": total_purchases_qty,
        "total_sales": total_sales_qty,
        "net_stock_change": net_stock_change,
        "item_summary": item_summary[:15],
        "current_time": current_time,
    }
    return render(request, "reports.html", context)
