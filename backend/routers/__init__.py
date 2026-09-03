"""HTTP routers, one per area of the product.

`main.py` mounts exactly this list, so adding an area means adding a module here
and one line there rather than growing a single thousand-line app file.
"""

from routers import auth, bot, credit, insurance, loans, platforms, tax, transactions

# Mount order is display order in the generated OpenAPI docs: the flow a worker
# actually walks, then the lender's half, then the advisory extras.
ALL_ROUTERS = (
    auth.router,
    transactions.router,
    platforms.router,
    credit.router,
    loans.router,
    insurance.router,
    tax.router,
    bot.router,
)

__all__ = ["ALL_ROUTERS"]
