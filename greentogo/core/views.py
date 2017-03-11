from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.core.urlresolvers import reverse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

import pinax.stripe.models as pinax_models
from pinax.stripe.actions import customers, invoices, subscriptions

from .forms import NewSubscriptionForm, SubscriptionPlanForm, UserForm
from .models import Subscription, get_plans


def index(request):
    return render(request, 'core/index_logged_out.html')


@login_required
def account(request):
    if request.method == "POST":
        form = UserForm(request.POST, instance=request.user)
        if form.is_valid():
            messages.success(request, "You have updated your user information.")
            form.save()
            return redirect(reverse("account"))
    else:
        form = UserForm(instance=request.user)

    customer = request.user.customer
    subscriptions = [
        {
            "id": subscription.stripe_id,
            "name": subscription.plan_display(),
            "price": subscription.total_amount,
            "ends": subscription.current_period_end,
            "auto_renew": not subscription.cancel_at_period_end,
        }
        for subscription in customer.subscription_set.filter(ended_at=None)
        .order_by("-current_period_end")
    ]

    return render(
        request, 'core/account.html',
        {"form": form,
         "customer": customer,
         "subscriptions": subscriptions}
    )


@login_required
def change_password(request):
    if request.method == "POST":
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Your password has been changed.")
            return redirect(reverse('account'))
    else:
        form = SetPasswordForm(request.user)

    return render(request, "core/change_password.html", {"form": form})


@login_required
def subscription(request, sub_id):
    subscription = Subscription.lookup_by_customer_and_sub_id(request.user.customer, sub_id)
    return render(request, "core/subscription.html", {
        "subscription": subscription,
    })


@login_required
def add_subscription(request):
    if request.method == "POST":
        form = NewSubscriptionForm(request.POST)
        if form.is_valid():
            plan = pinax_models.Plan.objects.get(stripe_id=form.cleaned_data['plan'])
            subscriptions.create(
                customer=request.user.customer, plan=plan, token=form.cleaned_data['token']
            )
            messages.success(
                request, "You have added a subscription to the plan {}.".format(plan.name)
            )
            return redirect(reverse('account'))
    else:
        form = NewSubscriptionForm()

    return render(
        request, "core/add_subscription.html", {
            "form": form,
            "plans": get_plans(),
            "email": request.user.email,
            "stripe_key": settings.STRIPE_PUBLISHABLE_KEY
        }
    )


@login_required
def change_subscription_plan(request, sub_id):
    customer = request.user.customer
    subscription = Subscription.lookup_by_customer_and_sub_id(customer, sub_id)
    if request.method == "POST":
        form = SubscriptionPlanForm(request.POST)
        if form.is_valid():
            plan = pinax_models.Plan.objects.get(stripe_id=form.cleaned_data['plan'])
            subscriptions.update(
                subscription=subscription, plan=plan, prorate=True, charge_immediately=True
            )
            invoices.create(customer=customer)
            messages.success(request, "Your plan has been updated to {}.".format(plan.name))
            return redirect(reverse('account'))
    else:
        form = SubscriptionPlanForm()

    return render(
        request, "core/subscription_plan.html", {"subscription": subscription,
                                                 "form": form}
    )


@login_required
def cancel_subscription(request, sub_id):
    subscription = Subscription.lookup_by_customer_and_sub_id(request.user.customer, sub_id)
    if request.method == "POST":
        subscriptions.cancel(subscription, at_period_end=False)
        messages.success(request, "Your subscription has been cancelled.")
        return redirect(reverse('account'))

    return render(request, "core/cancel_subscription.html", {"subscription": subscription})
