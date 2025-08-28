print("OCR Tool")
from mistralai import Mistral
import os

api_key = "KEY"

doc_id = "EXAMPLE_ID"

client = Mistral(api_key=api_key)

if(not doc_id)
    print("Uploading File...")
    uploaded_pdf = client.files.upload(
        file={
            "file_name": "uploaded_file.pdf",
            "content": open("uploaded_file.pdf", "rb"),
        },
        purpose="ocr"
    )  

    print(f"doc id: {uploaded_pdf.id}")

    print("Getting URL...")
    signed_url = client.files.get_signed_url(file_id=uploaded_pdf.id)
else
    signed_url = client.files.get_signed_url(file_id=doc_id)


print("Running OCR...")
response = client.ocr.process(
    model="mistral-ocr-latest",
    document={
        "type": "document_url",
        "document_url": signed_url.url,
    },
    include_image_base64=True
)

markdown= "\n\n".join([f"### Page {i+1}\n{response.pages[i].markdown}" for i in range(len(response.pages))])

print(markdown)