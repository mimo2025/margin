"""Original fictional fixtures. Each new application starts at version one."""

from app.models import Document


def sample_documents() -> list[Document]:
    return [
        Document(
            id="services",
            title="Fictional Services Agreement",
            text=(
                "FICTIONAL SERVICES AGREEMENT\n"
                "Demo text only. The parties and terms below are fictional.\n\n"
                "Parties: Cedar Kite Studio and Harbor Lantern Labs.\n\n"
                "1. Services\n"
                "Cedar Kite Studio will deliver a monthly design report.\n\n"
                "2. Payment\n"
                "Harbor Lantern Labs will pay each invoice within thirty (30) days of receipt.\n\n"
                "3. Termination\n"
                "Either party may end this agreement with thirty (30) days of written notice.\n\n"
                "4. Confidentiality\n"
                "Each party will protect the other party's confidential information.\n"
            ),
        ),
        Document(
            id="license",
            title="Fictional Software License",
            text=(
                "FICTIONAL SOFTWARE LICENSE\n"
                "Demo text only. The parties and terms below are fictional.\n\n"
                "Parties: Paper Comet Software and Meadow Compass Co.\n\n"
                "1. License\n"
                "Paper Comet Software grants access to its demonstration planning tool.\n\n"
                "2. Payment\n"
                "License fees are due within thirty (30) days of the invoice date.\n\n"
                "3. Renewal\n"
                "The parties may agree in writing to renew for one additional year.\n"
            ),
        ),
        Document(
            id="consulting",
            title="Fictional Consulting Agreement",
            text=(
                "FICTIONAL CONSULTING AGREEMENT\n"
                "Demo text only. The parties and terms below are fictional.\n\n"
                "Parties: Blue Pebble Advisory and Orchard Signal Works.\n\n"
                "1. Deliverables\n"
                "Blue Pebble Advisory will prepare a fictional operations workshop.\n\n"
                "2. Review\n"
                "Orchard Signal Works will provide feedback within ten (10) days.\n\n"
                "3. Payment\n"
                "Payment is due within fifteen (15) days of workshop completion.\n"
            ),
        ),
    ]
