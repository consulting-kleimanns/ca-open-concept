# my-van-ha – Home Assistant für „Mein Master“ (Demo je Interessent)
#
# Bauen (aus der Wurzel von ca-open-concept):
#   docker build -f demo/image/Dockerfile -t ghcr.io/consulting-kleimanns/my-van-ha:dev .
#
# Enthält: ca_camper (Energiemanager), ca_camper_sim (Simulation der Fahrzeugtechnik),
# Bubble Card, Theme „CA Camping“, Seed-Konfiguration und Standard-Dashboards.
# Beim Start gleicht 10-my-van die verwalteten Teile in /config ab; die Daten des
# Interessenten (.storage, eigene Automationen, Szenen …) bleiben unangetastet.
ARG HA_VERSION=2026.11.1

FROM alpine/git:latest AS bubble
ARG BUBBLE_CARD_VERSION=v3.4.3
RUN git clone --depth 1 --branch ${BUBBLE_CARD_VERSION} https://github.com/Clooos/Bubble-Card /src

FROM ghcr.io/home-assistant/home-assistant:${HA_VERSION}
ARG MYVAN_VERSION=dev
ENV MYVAN_IMAGE_VERSION=${MYVAN_VERSION}
LABEL org.opencontainers.image.source="https://github.com/consulting-kleimanns/ca-open-concept" \
      org.opencontainers.image.title="my-van-ha" \
      org.opencontainers.image.description="Home Assistant mit CA-Camper-Simulation für my-van.ca-camping.de" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY --from=bubble /src/dist/ /opt/my-van/www/bubble-card/
COPY custom_components/ca_camper /opt/my-van/custom_components/ca_camper
COPY demo/custom_components/ca_camper_sim /opt/my-van/custom_components/ca_camper_sim
COPY demo/image/seed /opt/my-van/seed
COPY demo/image/themes /opt/my-van/themes
COPY demo/image/www /opt/my-van/www/ca
COPY demo/image/rootfs/ /
RUN chmod 0755 /etc/cont-init.d/10-my-van \
 && find /opt/my-van -name __pycache__ -prune -exec rm -rf {} + \
 && echo "${MYVAN_VERSION}" > /opt/my-van/VERSION
