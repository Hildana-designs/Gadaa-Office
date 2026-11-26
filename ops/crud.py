"""
Simple list / add / edit screens for every record type, from one description
per type. Lists support search as you type (HTMX).
"""
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse

from core import audit, roles
from core.crypto import EncryptedTextField
from core.models import Choice


class Resource:
    model = None
    slug = ""
    title = ""
    list_fields = []
    search_fields = []
    form_fields = "__all__"
    exclude = ()
    choice_lists = {}  # field name -> Choice list name
    sensitive = False  # hidden from the Accountant
    trip_filter = True

    def __init__(self):
        self.title = self.title or self.model._meta.verbose_name_plural.capitalize()

    # ---- forms
    def form_class(self):
        resource = self

        class Form(forms.ModelForm):
            class Meta:
                model = resource.model
                fields = resource.form_fields
                exclude = resource.exclude if resource.form_fields == "__all__" else None
                widgets = {}

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for name, list_name in resource.choice_lists.items():
                    if name in self.fields:
                        values = Choice.values(list_name)
                        current = getattr(self.instance, name, "")
                        if current and current not in values:
                            values.append(current)
                        self.fields[name] = forms.ChoiceField(
                            choices=[("", "---------")] + [(v, v) for v in values],
                            required=self.fields[name].required, label=self.fields[name].label)
                for name, field in self.fields.items():
                    model_field = resource.model._meta.get_field(name) if name in [f.name for f in resource.model._meta.fields] else None
                    if isinstance(field.widget, forms.DateInput) or (model_field and model_field.get_internal_type() == "DateField"):
                        field.widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
                    if isinstance(field.widget, forms.Textarea):
                        field.widget.attrs["rows"] = 3
                    if model_field and isinstance(model_field, EncryptedTextField):
                        field.widget = forms.TextInput(attrs={"autocomplete": "off"})

        return Form

    # ---- permissions
    def check_view(self, user):
        roles.require(roles.can_view, user)
        if self.sensitive and not roles.can_see_passports(user):
            raise PermissionDenied

    def check_edit(self, user):
        roles.require(roles.can_edit, user)

    # ---- views
    def queryset(self, request):
        qs = self.model.objects.all()
        q = request.GET.get("q", "").strip()
        if q and self.search_fields:
            cond = Q()
            for f in self.search_fields:
                cond |= Q(**{f"{f}__icontains": q})
            qs = qs.filter(cond)
        trip = request.GET.get("trip")
        if trip and self.trip_filter and "trip" in [f.name for f in self.model._meta.fields]:
            qs = qs.filter(trip_id=trip)
        return qs

    def columns(self):
        cols = []
        for name in self.list_fields:
            f = self.model._meta.get_field(name)
            cols.append((name, f.verbose_name.capitalize()))
        return cols

    def list_view(self, request):
        self.check_view(request.user)
        page = Paginator(self.queryset(request), 50).get_page(request.GET.get("page"))
        rows = [(obj, [self.display(obj, n) for n, _ in self.columns()]) for obj in page]
        ctx = {"r": self, "page": page, "rows": rows, "q": request.GET.get("q", ""), "columns": self.columns()}
        template = "ops/_list_rows.html" if request.headers.get("HX-Request") else "ops/list.html"
        return render(request, template, ctx)

    def display(self, obj, name):
        field = obj._meta.get_field(name)
        value = getattr(obj, name)
        if field.choices:
            return getattr(obj, f"get_{name}_display")()
        if isinstance(field, EncryptedTextField):
            return "•••• " + value[-3:] if value else ""
        if value is True:
            return "Yes"
        if value is False:
            return "No"
        return "" if value is None else value

    def edit_view(self, request, pk=None):
        obj = get_object_or_404(self.model, pk=pk) if pk else None
        if request.method == "POST":
            self.check_edit(request.user)
        else:
            self.check_view(request.user)
        Form = self.form_class()
        initial = {}
        if not obj and request.GET.get("trip"):
            initial["trip"] = request.GET["trip"]
        form = Form(request.POST or None, request.FILES or None, instance=obj, initial=initial)
        if not roles.can_edit(request.user):
            for f in form.fields.values():
                f.disabled = True
        if request.method == "POST" and form.is_valid():
            saved = form.save()
            messages.success(request, f"Saved {saved}.")
            nxt = request.POST.get("next")
            if nxt and nxt.startswith("/"):
                return redirect(nxt)
            if hasattr(saved, "get_absolute_url"):
                return redirect(saved.get_absolute_url())
            return redirect(reverse(f"ops:{self.slug}_list"))
        if obj and self.sensitive:
            audit.log("view_sensitive", obj, note="opened record with passport / ID data")
        return render(request, "ops/form.html", {"r": self, "form": form, "obj": obj, "next": request.GET.get("next", "")})

    def delete_view(self, request, pk):
        roles.require(roles.is_admin, request.user)
        obj = get_object_or_404(self.model, pk=pk)
        if request.method == "POST":
            label = str(obj)
            obj.delete()
            messages.success(request, f"Deleted {label}.")
            return redirect(reverse(f"ops:{self.slug}_list"))
        return render(request, "ops/confirm_delete.html", {"r": self, "obj": obj})

    def urls(self):
        return [
            path(f"{self.slug}/", self.list_view, name=f"{self.slug}_list"),
            path(f"{self.slug}/new/", self.edit_view, name=f"{self.slug}_new"),
            path(f"{self.slug}/<int:pk>/", self.edit_view, name=f"{self.slug}_edit"),
            path(f"{self.slug}/<int:pk>/delete/", self.delete_view, name=f"{self.slug}_delete"),
        ]
