package main

import (
	"bytes"
	"encoding/base64"
	"image"
	"image/color"
	"image/draw"
	"image/png"

	_ "embed"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"golang.org/x/image/font"
	"golang.org/x/image/font/opentype"
	"golang.org/x/image/math/fixed"
)

//go:embed arial.ttf
var arial []byte

func Handler(request events.APIGatewayProxyRequest) (events.APIGatewayProxyResponse, error) {
	var text = request.QueryStringParameters["text"]

	var (
		width, height = 200, 100
		captcha       = image.NewRGBA(image.Rect(0, 0, width, height))
	)

	draw.Draw(captcha, captcha.Bounds(), image.White, image.Point{}, draw.Src)

	var (
		f   *opentype.Font
		err error
	)

	if f, err = opentype.Parse(arial); err != nil {
		panic(err)
	}

	var (
		face     font.Face
		fontSize = 24.0
	)

	if face, err = opentype.NewFace(f, &opentype.FaceOptions{Size: fontSize, DPI: 72}); err != nil {
		panic(err)
	}
	defer face.Close()

	var (
		drawer = &font.Drawer{
			Dst:  captcha,
			Src:  image.NewUniform(color.Black),
			Face: face,
		}

		totalTextWidth = font.MeasureString(face, text).Ceil()
		spacing        = (width - totalTextWidth) / (len(text) + 1)
		x              = spacing
		y              = (height + int(fontSize)) / 2
		char           rune
	)

	for _, char = range text {
		drawer.Dot = fixed.Point26_6{X: fixed.I(x), Y: fixed.I(y)}
		drawer.DrawString(string(char))
		x += font.MeasureString(face, string(char)).Ceil() + spacing
	}

	var buffer bytes.Buffer
	if err = png.Encode(&buffer, captcha); err != nil {
		panic(err)
	}

	return events.APIGatewayProxyResponse{StatusCode: 200, Headers: map[string]string{"Content-Type": "image/png"}, Body: base64.StdEncoding.EncodeToString(buffer.Bytes()), IsBase64Encoded: true}, nil
}

func main() {
	lambda.Start(Handler)
}
