FROM gcr.io/distroless/python3-debian13@sha256:ed3a4beb46f8f8baac068743ba1b1f95ea3f793422129cf6dd23967f779b6018
WORKDIR /app
COPY services/phase4-proof/app.py /app/app.py
USER 65532:65532
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
ENTRYPOINT ["/usr/bin/python3", "/app/app.py"]
