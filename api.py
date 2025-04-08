from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from PIL import Image
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from pdf2docx import Converter
from docx2pdf import convert
import os
import tempfile
import shutil
import platform
import subprocess
from typing import List
import uuid
import atexit

app = FastAPI(
    title="PDF Araç Seti API",
    description="PDF dönüştürme, birleştirme ve sıkıştırma işlemleri için API",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tüm originlere izin ver
    allow_credentials=True,
    allow_methods=["*"],  # Tüm HTTP metodlarına izin ver
    allow_headers=["*"],  # Tüm headerlara izin ver
)

# Geçici dosyalar için klasör
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

def cleanup_temp_files():
    """Geçici dosyaları temizle"""
    if os.path.exists(TEMP_DIR):
        for file in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Hata: {e}")

# Uygulama kapandığında geçici dosyaları temizle
atexit.register(cleanup_temp_files)

@app.post("/images-to-pdf/", tags=["Görsel İşlemleri"])
async def convert_images_to_pdf(images: List[UploadFile] = File(...)):
    """
    Birden fazla görseli PDF'e dönüştür
    """
    if not images:
        raise HTTPException(status_code=400, detail="Lütfen en az bir görsel yükleyin")
    
    temp_files = []
    output_pdf = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.pdf")
    
    try:
        # İlk görseli aç ve RGB'ye dönüştür
        first_image_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{images[0].filename}")
        temp_files.append(first_image_path)
        
        with open(first_image_path, "wb") as f:
            shutil.copyfileobj(images[0].file, f)
        
        first_image = Image.open(first_image_path)
        if first_image.mode != 'RGB':
            first_image = first_image.convert('RGB')
        
        # Diğer görselleri hazırla
        other_images = []
        for img in images[1:]:
            img_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{img.filename}")
            temp_files.append(img_path)
            
            with open(img_path, "wb") as f:
                shutil.copyfileobj(img.file, f)
            
            image = Image.open(img_path)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            other_images.append(image)
        
        # PDF olarak kaydet
        first_image.save(output_pdf, "PDF", resolution=100.0, save_all=True, append_images=other_images)
        
        # Dosyayı gönder
        return FileResponse(
            output_pdf, 
            filename="converted.pdf", 
            media_type="application/pdf",
            background=None  # Senkron işlem için
        )
    
    except Exception as e:
        # Hata durumunda geçici dosyaları temizle
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        if os.path.exists(output_pdf):
            os.unlink(output_pdf)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/merge-pdfs/", tags=["PDF İşlemleri"])
async def merge_pdfs(pdfs: List[UploadFile] = File(...)):
    """
    Birden fazla PDF dosyasını birleştir
    """
    if len(pdfs) < 2:
        raise HTTPException(status_code=400, detail="Lütfen en az 2 PDF dosyası yükleyin")
    
    temp_paths = []
    output_pdf = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.pdf")
    
    try:
        # PDF'leri geçici dosyalara kaydet
        for pdf in pdfs:
            temp_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{pdf.filename}")
            temp_paths.append(temp_path)
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(pdf.file, f)
        
        # PDF'leri birleştir
        merger = PdfMerger()
        for path in temp_paths:
            merger.append(path)
        
        merger.write(output_pdf)
        merger.close()
        
        return FileResponse(
            output_pdf, 
            filename="merged.pdf", 
            media_type="application/pdf",
            background=None
        )
    
    except Exception as e:
        # Hata durumunda geçici dosyaları temizle
        for temp_file in temp_paths:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
        if os.path.exists(output_pdf):
            os.unlink(output_pdf)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/pdf-to-word/", tags=["Dönüştürme"])
async def convert_pdf_to_word(pdf: UploadFile = File(...)):
    """
    PDF dosyasını Word dosyasına dönüştür
    """
    if not pdf.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Lütfen PDF dosyası yükleyin")
    
    temp_pdf = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{pdf.filename}")
    output_docx = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.docx")
    
    try:
        # PDF'i geçici dosyaya kaydet
        with open(temp_pdf, "wb") as f:
            shutil.copyfileobj(pdf.file, f)
        
        # PDF'i Word'e dönüştür
        cv = Converter(temp_pdf)
        cv.convert(output_docx)
        cv.close()
        
        return FileResponse(
            output_docx, 
            filename="converted.docx", 
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            background=None
        )
    
    except Exception as e:
        # Hata durumunda geçici dosyaları temizle
        if os.path.exists(temp_pdf):
            os.unlink(temp_pdf)
        if os.path.exists(output_docx):
            os.unlink(output_docx)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compress-pdf/", tags=["PDF İşlemleri"])
async def compress_pdf(
    pdf: UploadFile = File(...),
    compression_level: int = 2  # 1: düşük, 2: orta, 3: yüksek, 4: maksimum
):
    """
    PDF dosyasını sıkıştır
    """
    if not pdf.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Lütfen PDF dosyası yükleyin")
    
    if compression_level not in [1, 2, 3, 4]:
        raise HTTPException(status_code=400, detail="Geçersiz sıkıştırma seviyesi")
    
    temp_pdf = os.path.join(TEMP_DIR, f"{uuid.uuid4()}_{pdf.filename}")
    output_pdf = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.pdf")
    
    try:
        # PDF'i geçici dosyaya kaydet
        with open(temp_pdf, "wb") as f:
            shutil.copyfileobj(pdf.file, f)
        
        # PDF'i oku ve sıkıştır
        reader = PdfReader(temp_pdf)
        writer = PdfWriter()
        
        # Sıkıştırma seviyesine göre ayarlar
        if compression_level == 1:
            compress_images = False
            image_quality = 100
        elif compression_level == 2:
            compress_images = True
            image_quality = 80
        elif compression_level == 3:
            compress_images = True
            image_quality = 60
        else:
            compress_images = True
            image_quality = 30
        
        # Sayfaları işle
        for page in reader.pages:
            writer.add_page(page)
        
        # PDF'i kaydet
        writer.write(output_pdf)
        
        return FileResponse(
            output_pdf, 
            filename="compressed.pdf", 
            media_type="application/pdf",
            background=None
        )
    
    except Exception as e:
        # Hata durumunda geçici dosyaları temizle
        if os.path.exists(temp_pdf):
            os.unlink(temp_pdf)
        if os.path.exists(output_pdf):
            os.unlink(output_pdf)
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """Uygulama başladığında geçici dosyaları temizle"""
    cleanup_temp_files()
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"mesaj": "API'ye Hoş Geldiniz "}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
