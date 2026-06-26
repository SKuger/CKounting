import pandas as pd
import os

os.makedirs('static', exist_ok=True)
df = pd.DataFrame({'NIT': [900123456, 800987654, 123456789]})
df.to_excel('static/plantilla_rut.xlsx', index=False)
print("Template created")
