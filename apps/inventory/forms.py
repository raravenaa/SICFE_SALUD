import uuid
from decimal import Decimal

from django import forms
from django.forms import formset_factory

from .access import warehouses_for
from .models import Movement, Product, Warehouse


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["code", "name", "unit", "category", "avis_code", "active"]


class MovementForm(forms.Form):
    warehouse = forms.ModelChoiceField(label="Bodega", queryset=Warehouse.objects.none())
    kind = forms.ChoiceField(label="Tipo", choices=Movement.Kind.choices)
    reference = forms.CharField(label="Referencia documental", max_length=150)
    reason = forms.CharField(
        label="Motivo", max_length=300, widget=forms.Textarea(attrs={"rows": 2})
    )
    request_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["warehouse"].queryset = warehouses_for(user).filter(active=True)


class InventoryCountForm(forms.Form):
    warehouse = forms.ModelChoiceField(label="Bodega", queryset=Warehouse.objects.none())
    file = forms.FileField(
        label="Archivo Excel (.xlsx)",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["warehouse"].queryset = warehouses_for(user).filter(active=True)

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if not uploaded_file.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Carga un archivo Excel con formato .xlsx.")
        if uploaded_file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar 5 MB.")
        return uploaded_file


class MovementLineForm(forms.Form):
    product = forms.ModelChoiceField(label="Producto", queryset=Product.objects.filter(active=True))
    lot_code = forms.CharField(label="Código de lote", max_length=80)
    expires_on = forms.DateField(
        label="Vencimiento", widget=forms.DateInput(attrs={"type": "date"})
    )
    quantity = forms.DecimalField(
        label="Cantidad", max_digits=15, decimal_places=3, min_value=Decimal("0.001")
    )
    unit_cost = forms.DecimalField(
        label="Costo unitario de ingreso",
        max_digits=18,
        decimal_places=6,
        min_value=Decimal("0"),
        required=False,
        help_text="Obligatorio para ingresos; dejar vacío en salidas.",
    )


MovementLineFormSet = formset_factory(
    MovementLineForm,
    extra=0,
    min_num=1,
    validate_min=True,
    max_num=50,
    validate_max=True,
    absolute_max=50,
    can_delete=True,
)
