from shipment_exceptions import example_request, process_shipment_update


def main() -> None:
    request = example_request()
    result = process_shipment_update(request)
    print(f"processed shipment {result.shipment_id} with status {result.status}")


if __name__ == "__main__":
    main()
