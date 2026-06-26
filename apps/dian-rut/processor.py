import asyncio
import pandas as pd
import os
import traceback
from scraper import perform_scraping

async def process_excel(file_path: str, file_id: str, client_id: str, send_log, active_jobs: dict):
    output_filename = f"resultados_{file_id}.xlsx"
    output_path = os.path.join("results", output_filename)
    active_jobs[file_id] = output_path
    
    try:
        await send_log(client_id, "info", {"message": "Iniciando lectura del archivo Excel..."})
        df = pd.read_excel(file_path)
        
        if 'NIT' not in df.columns:
            await send_log(client_id, "error", {"message": "El archivo no contiene la columna 'NIT'"})
            return
        
        # Estandarizar NIT a string limpio para el merge
        df['NIT'] = df['NIT'].apply(
            lambda x: str(int(x)).strip() if isinstance(x, float) and pd.notna(x) else str(x).strip()
        )
        df['NIT'] = df['NIT'].astype(str).str.strip()
        df = df[df['NIT'].str.lower() != "nan"]  # Filtrar filas vacías
        
        nits = df['NIT'].dropna().unique().tolist()
        total_nits = len(nits)
        await send_log(client_id, "info", {"message": f"Se encontraron {total_nits} NITs únicos para consultar."})
        
        results = []
        
        async def save_callback(current_results):
            results_df = pd.DataFrame(current_results)
            if results_df.empty:
                return
            
            # Garantizar compatibilidad de tipos antes del merge
            results_df['NIT'] = results_df['NIT'].astype(str).str.strip()
            df['NIT'] = df['NIT'].astype(str).str.strip()
            
            # Validación de extracción
            if results_df.empty:
                print("[WARN] save_callback: No se extrajeron datos todavía.")
                return
            
            # LEFT MERGE: preserva todos los NITs originales aunque no hayan sido consultados aún
            final_df = df.merge(results_df, on='NIT', how='left')
            final_df.to_excel(output_path, index=False)
        
        await perform_scraping(nits, results, client_id, send_log, save_callback)
        
        # Guardado final garantizado
        if results:
            results_df = pd.DataFrame(results)
            results_df['NIT'] = results_df['NIT'].astype(str).str.strip()
            df['NIT'] = df['NIT'].astype(str).str.strip()
            final_df = df.merge(results_df, on='NIT', how='left')
            final_df.to_excel(output_path, index=False)
            await send_log(client_id, "info", {"message": f"Excel guardado con {len(results_df)} resultados."})
        else:
            await send_log(client_id, "error", {"message": "Advertencia: No se extrajeron resultados para guardar."})
        
        await send_log(client_id, "done", {"message": "Proceso finalizado con éxito.", "download_url": f"/download/{output_filename}"})
        
    except Exception as e:
        error_trace = traceback.format_exc()
        await send_log(client_id, "error", {"message": f"Error fatal procesando el archivo: {str(e)}", "trace": error_trace})
        print(error_trace)
