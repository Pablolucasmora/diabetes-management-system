# DayBetes_food/routes/__init__.py
"""
Routes package for DayBetes application.

This package contains all route setup functions for different modules:
- auth_routes: Authentication and authorization
- food_routes: Food catalog and management
- cart_routes: Shopping cart operations
- main_routes: Main navigation routes
- stats_routes: Statistics and analytics
- settings_routes: User settings
"""

from .auth_routes import setup_auth_routes
from .cart_routes import setup_cart_routes
from .food_routes import setup_food_routes
from .main_routes import setup_main_routes
from .settings_routes import setup_settings_routes
from .stats_routes import setup_stats_routes

__all__ = [
    'setup_auth_routes',
    'setup_cart_routes', 
    'setup_food_routes',
    'setup_main_routes',
    'setup_settings_routes',
    'setup_stats_routes',
]