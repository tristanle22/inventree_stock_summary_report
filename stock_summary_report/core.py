"""Print stock flow between a date range"""

from plugin import InvenTreePlugin

from plugin.mixins import ReportMixin, SettingsMixin, UserInterfaceMixin

from . import PLUGIN_VERSION

from report.models import ReportTemplate
from stock.models import StockLocation, StockItem

from decimal import Decimal
from datetime import datetime
from django import template
from django.template.defaultfilters import stringfilter
from django.utils import timezone

register = template.Library()

@register.filter
def sum_deltas(entries, delta_type):
    """Sum up delta values of a specific type from tracking entries."""
    return sum(entry['deltas'].get(delta_type, 0) for entry in entries)

class StockSummaryReport(ReportMixin, SettingsMixin, UserInterfaceMixin, InvenTreePlugin):

    """StockSummaryReport - custom InvenTree plugin."""

    # Plugin metadata
    TITLE = "Stock Summary Report"
    NAME = "StockSummaryReport"
    SLUG = "stock-summary-report"
    DESCRIPTION = "Print stock flow between a date range"
    VERSION = PLUGIN_VERSION

    # Additional project information
    AUTHOR = "Tristan Le"
    WEBSITE = "https://github.com/tristanle22/inventree_stock_summary_report"
    LICENSE = "MIT"

    # Optionally specify supported InvenTree versions
    # MIN_VERSION = '0.18.0'
    # MAX_VERSION = '2.0.0'

    # Render custom UI elements to the plugin settings page
    ADMIN_SOURCE = "Settings.js:renderPluginSettings"
    
    
    # Plugin settings (from SettingsMixin)
    # Ref: https://docs.inventree.org/en/stable/extend/plugins/settings/
    SETTINGS = {
        'START_DATE': {
            'name': 'Start Date',
            'description': 'Start date for stock tracking (DD/MM/YYYY)',
            'validator': str,
            'default': '01/01/2024',
        },
        'END_DATE': {
            'name': 'End Date',
            'description': 'End date for stock tracking (DD/MM/YYYY)',
            'validator': str,
            'default': '31/12/2024',
        }
    }
    
    
    
    # Custom report context (from ReportMixin)
    # Ref: https://docs.inventree.org/en/stable/extend/plugins/report/
    def add_label_context(self, label_instance, model_instance, request, context, **kwargs):
        """Add custom context data to a label rendering context."""
        
        # Add custom context data to the label rendering context
        context['foo'] = 'label_bar'

    def add_report_context(self, report_instance, model_instance, request, context, **kwargs):
        """Add custom context data to a report rendering context."""
        
        # Ensure we have a StockLocation instance
        if not isinstance(model_instance, StockLocation):
            return
        
        # Get date range from settings
        start_date, end_date, start_date_str, end_date_str = self.get_date_range()
        
        # Get all stock items in this location and its sub-locations
        location_tree = model_instance.get_descendants(include_self=True)
        stock_items = StockItem.objects.filter(
            location__in=location_tree
        ).select_related('part', 'location').distinct()
        
        # Process each stock item
        stock_summary = []
        for item in stock_items:
            # Get tracking entries within date range
            tracking_entries = item.tracking_info.filter(
                date__gte=start_date,
                date__lte=end_date
            ).order_by('date')
            
            sum_added = 0
            sum_removed = 0
            if tracking_entries.exists():
                # Calculate sum of added deltas
                sum_added = sum(
                    entry.deltas.get('added', 0) 
                    for entry in tracking_entries 
                    if hasattr(entry, 'deltas')
                )

                sum_removed = sum(
                    entry.deltas.get('removed', 0) 
                    for entry in tracking_entries 
                    if hasattr(entry, 'deltas')
                )
            
            start_quantity = item.quantity - Decimal(str(sum_added)) + Decimal(str(sum_removed))
            purchase_price = item.purchase_price if item.purchase_price else 0
            stock_summary.append({
                'stock_item': item,
                'part': item.part,
                'part_id': item.part.id,
                'location': item.location.name,
                'location_id': item.location.id,
                'quantity': item.quantity,
                'quantity_value': item.quantity * purchase_price,
                'start_quantity': start_quantity,
                'start_quantity_value': start_quantity * purchase_price,
                'sum_added': sum_added,
                'sum_added_value': sum_added * purchase_price,
                'sum_removed': sum_removed,
                'sum_removed_value': sum_removed * purchase_price,
                'tracking_entries': [
                    {
                        'date': entry.date,
                        'deltas': entry.deltas,
                        'notes': entry.notes,
                    } for entry in tracking_entries
                ],
                'first_entry': tracking_entries.first(),
                'last_entry': tracking_entries.last(),
            })
        
        # Add the summary to the report context
        context['stock_summary'] = stock_summary
        context['date_range'] = {
            'start': start_date_str,
            'end': end_date_str
        }
        context['location'] = {
            'name': model_instance.name,
            'id': model_instance.id
        }
        return context

    def report_callback(self, template, instance, report, request, **kwargs):
        """Callback function called after a report is generated."""
        ...

    # User interface elements (from UserInterfaceMixin)
    # Ref: https://docs.inventree.org/en/stable/extend/plugins/ui/
    
    # Custom UI panels
    def get_ui_panels(self, request, context: dict, **kwargs):
        """Return a list of custom panels to be rendered in the InvenTree user interface."""

        panels = []

        # Only display this panel for the 'part' target
        if context.get('target_model') == 'part':
            panels.append({
                'key': 'stock-summary-report-panel',
                'title': 'Stock Summary Report',
                'description': 'Custom panel description',
                'icon': 'ti:mood-smile:outline',
                'source': self.plugin_static_file('Panel.js:renderStockSummaryReportPanel'),
                'context': {
                    # Provide additional context data to the panel
                    'settings': self.get_settings_dict(),
                    'foo': 'bar'
                }
            })
        
        return panels
    
    # Custom dashboard items
    def get_ui_dashboard_items(self, request, context: dict, **kwargs):
        """Return a list of custom dashboard items to be rendered in the InvenTree user interface."""

        # Example: only display for 'staff' users
        if not request.user or not request.user.is_staff:
            return []
        
        items = []

        items.append({
            'key': 'stock-summary-report-dashboard',
            'title': 'Stock Summary Report Dashboard Item',
            'description': 'Custom dashboard item',
            'icon': 'ti:dashboard:outline',
            'source': self.plugin_static_file('Dashboard.js:renderStockSummaryReportDashboardItem'),
            'context': {
                # Provide additional context data to the dashboard item
                'settings': self.get_settings_dict(),
                'bar': 'foo'
            }
        })

        return items


    def get_date_range(self):
        """Get the date range from plugin settings."""
        settings = self.get_settings_dict()
        
        # Parse the date strings into timezone-aware datetime objects
        start_date = timezone.make_aware(
            datetime.strptime(settings.get('START_DATE', '01/01/2024'), '%d/%m/%Y')
        )
        end_date = timezone.make_aware(
            datetime.strptime(settings.get('END_DATE', '31/12/2024'), '%d/%m/%Y')
        )
        
        return start_date, end_date, settings.get('START_DATE', '01/01/2024'), settings.get('END_DATE', '31/12/2024')
