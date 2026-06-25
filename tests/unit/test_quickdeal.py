from app.services.properties.quickdeal import parse_quickdeal_feed


def test_parse_quickdeal_yandex_offer() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <realty-feed xmlns="http://webmaster.yandex.ru/schemas/feed/realty/2010-06">
      <offer internal-id="QD_REALTY_1">
        <type>аренда</type>
        <qd_id>1</qd_id>
        <category>коммерческая</category>
        <commercial-type>warehouse</commercial-type>
        <location>
          <locality-name>Новосибирск</locality-name>
          <sub-locality-name>Кировский</sub-locality-name>
          <address>улица Мира, дом 1</address>
        </location>
        <sales-agent>
          <name>Иван</name>
          <phone>+79990000000</phone>
          <email>agent@example.com</email>
        </sales-agent>
        <price><value>200000</value><period>месяц</period></price>
        <area><value>300</value><unit>кв. м</unit></area>
        <image default="1">https://example.com/photo.jpg</image>
        <description><![CDATA[<p>Теплый склад с отдельным входом</p>]]></description>
      </offer>
    </realty-feed>"""

    offers = parse_quickdeal_feed(xml)

    assert len(offers) == 1
    offer = offers[0]
    assert offer.id == "1"
    assert offer.qd_id == "1"
    assert offer.price == 200000
    assert offer.area == 300
    assert offer.district == "Кировский"
    assert offer.raw_json["deal_type"] == "rent"
    assert offer.raw_json["property_type"] == "commercial"
    assert offer.raw_json["photos"] == [{"url": "https://example.com/photo.jpg"}]
    assert "Теплый склад" in offer.description
