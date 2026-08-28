FROM gcr.io/distroless/python3-debian13@sha256:f2b206661cee3edb44f132d7f054a9ced96f671d8a973de0db750895c9acb2fb
WORKDIR /app
COPY services/phase4-proof/app.py /app/app.py
USER 65532:65532
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
ENTRYPOINT ["/usr/bin/python3", "/app/app.py"]
